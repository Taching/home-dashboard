from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select

from app.core.settings import settings
from app.database.models import DailyWellbeingCheckIn, TrainingExercise, TrainingMetric, TrainingSession
from app.database.session import SessionLocal


class TrainingNotionSync:
    def __init__(self, session_factory=SessionLocal, client: httpx.Client | None = None) -> None:
        self._session_factory = session_factory
        self._client = client
        self._timezone = ZoneInfo(settings.timezone)

    def configured(self) -> bool:
        return bool(settings.notion_token and settings.notion_training_data_source_id)

    def sync_due(self, limit: int = 25) -> int:
        if not self.configured():
            return 0
        with self._session_factory() as session:
            rows = list(session.scalars(
                select(TrainingSession)
                .where(
                    (TrainingSession.notion_synced_at.is_(None))
                    | (TrainingSession.notion_synced_at < TrainingSession.updated_at)
                )
                .order_by(TrainingSession.updated_at)
                .limit(limit)
            ).all())
        synced = 0
        for row in rows:
            page_id = row.notion_page_id
            if row.status == "cancelled":
                if page_id:
                    self._request("PATCH", f"https://api.notion.com/v1/pages/{page_id}", {"in_trash": True})
                self._mark_synced(row.id, page_id)
                synced += 1
                continue
            page_id = page_id or self._find_page(row.id)
            payload = {"properties": self._properties(row)}
            if page_id:
                self._request("PATCH", f"https://api.notion.com/v1/pages/{page_id}", payload)
            else:
                payload.update({
                    "parent": {"type": "data_source_id", "data_source_id": settings.notion_training_data_source_id},
                    "children": self._metric_blocks(row.id),
                    "icon": {"type": "emoji", "emoji": "🥋"},
                })
                result = self._request("POST", "https://api.notion.com/v1/pages", payload)
                page_id = str(result.get("id", ""))
                if not page_id:
                    raise ValueError("Notion did not return a training page ID.")
            self._mark_synced(row.id, page_id)
            synced += 1
        return synced

    def _mark_synced(self, session_id: str, page_id: str | None) -> None:
        with self._session_factory() as session:
            current = session.get(TrainingSession, session_id)
            if current is not None:
                current.notion_page_id = page_id
                current.notion_synced_at = datetime.now(UTC)
                session.commit()

    def _properties(self, row: TrainingSession) -> dict:
        local_date = self._as_utc(row.start_at).astimezone(self._timezone).date()
        with self._session_factory() as session:
            exercises = list(session.scalars(
                select(TrainingExercise).where(TrainingExercise.session_id == row.id).order_by(TrainingExercise.position)
            ).all())
            metrics = list(session.scalars(
                select(TrainingMetric).where(TrainingMetric.session_id == row.id).order_by(TrainingMetric.metric_type, TrainingMetric.sequence)
            ).all())
            readiness = session.get(DailyWellbeingCheckIn, local_date)
        strength = "; ".join(self._exercise_text(item) for item in exercises)
        intervals = [item for item in metrics if item.metric_type.startswith("bike_")]
        interval_text = ", ".join(f"R{item.sequence or index + 1} {item.value:g} {item.unit}" for index, item in enumerate(intervals))
        value = lambda text: {"rich_text": [{"type": "text", "text": {"content": (text or "")[:2000]}}]}
        status = {
            "planned": "Planned", "in_progress": "Planned", "completed": "Completed",
            "partial": "Partial", "skipped": "Skipped", "recovery": "Recovery",
            "competition": "Competition", "cancelled": "Skipped",
        }.get(row.status, "Planned")
        props = {
            "Name": {"title": [{"type": "text", "text": {"content": self._title(row)}}]},
            "Local Session ID": value(row.id),
            "Date": {"date": {"start": self._as_utc(row.start_at).isoformat(), "end": self._as_utc(row.end_at).isoformat()}},
            "Planned Type": {"select": {"name": row.planned_type}},
            "Actual Type": {"select": {"name": row.actual_type}} if row.actual_type else {"select": None},
            "Status": {"select": {"name": status}},
            "Competition Phase": {"select": {"name": row.phase}},
            "Duration": {"number": row.estimated_minutes},
            "BJJ Rounds": {"number": row.target_rounds},
            "BJJ Round Length": {"number": row.round_length_seconds},
            "BJJ Rest Seconds": {"number": row.rest_seconds},
            "Strength Exercises": value(strength),
            "Bike Intervals": value(interval_text),
            "Session RPE": {"number": row.session_rpe},
            "Final Round Quality": {"number": row.final_round_quality},
            "Notes": value(row.notes or ""),
            "Coach Focus": value(" ".join(row.coach_focus or [])),
            "Rescheduled From": value(row.rescheduled_from_id or ""),
            "Calendar Event ID": value(row.apple_event_id or row.source_calendar_event_id or ""),
            "Body Weight": {"number": readiness.weight_kg if readiness else None},
            "Sleep Hours": {"number": readiness.sleep_hours if readiness else None},
            "Sleep Quality": {"number": readiness.sleep_quality if readiness else None},
            "Fatigue": {"number": readiness.fatigue if readiness else None},
            "Soreness": {"number": readiness.soreness if readiness else None},
            "Grip Fatigue": {"number": readiness.grip_fatigue if readiness else None},
            "Pain": {"checkbox": bool(readiness.pain) if readiness and readiness.pain is not None else False},
            "Readiness": {"number": readiness.readiness if readiness else None},
        }
        zone_metrics = {item.metric_type: item for item in metrics}
        props.update({
            "Zone 2 Average HR": {"number": zone_metrics.get("zone2_average_hr").value if zone_metrics.get("zone2_average_hr") else None},
            "Zone 2 Max HR": {"number": zone_metrics.get("zone2_max_hr").value if zone_metrics.get("zone2_max_hr") else None},
            "Zone 2 Distance": {"number": zone_metrics.get("zone2_distance").value if zone_metrics.get("zone2_distance") else None},
        })
        return props

    def _find_page(self, session_id: str) -> str | None:
        result = self._request(
            "POST", f"https://api.notion.com/v1/data_sources/{settings.notion_training_data_source_id}/query",
            {"filter": {"property": "Local Session ID", "rich_text": {"equals": session_id}}, "page_size": 1},
        )
        pages = result.get("results", [])
        return str(pages[0].get("id")) if pages else None

    def _metric_blocks(self, session_id: str) -> list[dict]:
        with self._session_factory() as session:
            metrics = list(session.scalars(
                select(TrainingMetric).where(TrainingMetric.session_id == session_id).order_by(TrainingMetric.metric_type, TrainingMetric.sequence)
            ).all())
        if not metrics:
            return []
        return [{
            "object": "block", "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": f"{item.metric_type} R{item.sequence or '-'}: {item.value:g} {item.unit}"}}]},
        } for item in metrics[:100]]

    def _request(self, method: str, url: str, payload: dict) -> dict:
        client = self._client or httpx.Client(timeout=15)
        close = self._client is None
        try:
            response = client.request(method, url, headers={
                "Authorization": f"Bearer {settings.notion_token}",
                "Notion-Version": "2026-03-11",
                "Content-Type": "application/json",
            }, json=payload)
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, dict) else {}
        finally:
            if close:
                client.close()

    @staticmethod
    def _exercise_text(item: TrainingExercise) -> str:
        details = [str(value) for value in (item.load_value, item.load_unit, f"{item.sets}×{item.reps}" if item.sets else item.reps) if value]
        return f"{item.name} {' '.join(details)}".strip()

    @staticmethod
    def _title(row: TrainingSession) -> str:
        return f"{row.start_at.date().isoformat()} · {row.planned_type.replace('_', ' ').title()}"

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
