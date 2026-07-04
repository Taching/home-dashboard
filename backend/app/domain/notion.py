from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Any, Literal
from zoneinfo import ZoneInfo

import httpx

from app.core.settings import settings

NotionStatus = Literal["not_configured", "ready", "unavailable"]


@dataclass(frozen=True)
class NotionTask:
    id: str
    title: str
    due_at: datetime | None
    is_overdue: bool
    status: str | None = None
    priority: str | None = None
    task_type: str | None = None


class NotionService:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client
        self._timezone = ZoneInfo(settings.timezone)
        self._last_error: str | None = None

    def configured(self) -> bool:
        return bool(settings.notion_token and (settings.notion_data_source_id or settings.notion_database_id))

    def status(self) -> NotionStatus:
        if not self.configured():
            return "not_configured"
        return "unavailable" if self._last_error else "ready"

    def today(self) -> tuple[NotionStatus, datetime | None, list[NotionTask]]:
        if not self.configured():
            return "not_configured", None, []
        try:
            pages = self._query_pages()
            now = datetime.now(self._timezone)
            today = now.date()
            tasks = [
                task for task in (self._page_to_task(page, today) for page in pages)
                if task is not None
            ]
            tasks.sort(key=self._sort_key)
            self._last_error = None
            return "ready", datetime.now(UTC), tasks
        except (httpx.HTTPError, AttributeError, ValueError, KeyError, TypeError) as error:
            self._last_error = str(error) or "Notion is unavailable."
            return "unavailable", datetime.now(UTC), []

    def _query_pages(self) -> list[dict[str, Any]]:
        assert settings.notion_token
        if settings.notion_data_source_id:
            url = f"https://api.notion.com/v1/data_sources/{settings.notion_data_source_id}/query"
            notion_version = "2026-03-11"
        else:
            url = f"https://api.notion.com/v1/databases/{settings.notion_database_id}/query"
            notion_version = "2022-06-28"
        client = self._client or httpx.Client(timeout=15)
        close_client = self._client is None
        try:
            response = client.post(
                url,
                headers={
                    "Authorization": f"Bearer {settings.notion_token}",
                    "Notion-Version": notion_version,
                    "Content-Type": "application/json",
                },
                json={"page_size": 100},
            )
            response.raise_for_status()
            return list(response.json().get("results", []))
        finally:
            if close_client:
                client.close()

    def _sort_key(self, task: NotionTask) -> tuple[int, bool, datetime, str]:
        return (
            self._priority_rank(task.priority),
            task.due_at is None,
            task.due_at or datetime.max.replace(tzinfo=UTC),
            task.title.lower(),
        )

    def _priority_rank(self, priority: str | None) -> int:
        value = (priority or "").lower()
        if "high" in value or "urgent" in value:
            return 0
        if "medium" in value or "normal" in value:
            return 1
        if "low" in value:
            return 2
        return 3

    def _page_to_task(self, page: dict[str, Any], today: date) -> NotionTask | None:
        properties = page.get("properties", {})
        if not isinstance(properties, dict) or self._is_done(properties):
            return None
        if not self._is_todo_status(properties):
            return None
        due_at = self._due_at(properties)
        due_date = due_at.astimezone(self._timezone).date() if due_at else None
        title = self._title(properties).strip()
        if not title:
            return None
        return NotionTask(
            id=str(page.get("id", "")),
            title=title,
            due_at=due_at,
            is_overdue=due_date is not None and due_date < today,
            status=self._property_name(properties, settings.notion_status_property),
            priority=self._property_name(properties, "Priority"),
            task_type=self._property_name(properties, settings.notion_type_property),
        )

    def _title(self, properties: dict[str, Any]) -> str:
        prop = properties.get(settings.notion_title_property) or next(
            (value for value in properties.values() if value.get("type") == "title"),
            {},
        )
        values = prop.get("title") or prop.get("rich_text") or []
        return "".join(str(item.get("plain_text", "")) for item in values)

    def _due_at(self, properties: dict[str, Any]) -> datetime | None:
        prop = properties.get(settings.notion_due_property) or next(
            (value for value in properties.values() if value.get("type") == "date"),
            None,
        )
        date_value = prop.get("date") if prop else None
        value = date_value.get("start") if isinstance(date_value, dict) else None
        if not value:
            return None
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = datetime.combine(parsed.date(), time.min, self._timezone)
        return parsed.astimezone(UTC)

    def _is_todo_status(self, properties: dict[str, Any]) -> bool:
        status = self._property_name(properties, settings.notion_status_property)
        if not status:
            return True
        value = status.strip().lower()
        return value in {"to do", "todo", "backlog"}

    def _is_done(self, properties: dict[str, Any]) -> bool:
        checkbox = properties.get(settings.notion_done_property)
        if checkbox and checkbox.get("type") == "checkbox":
            return bool(checkbox.get("checkbox"))
        status = properties.get(settings.notion_status_property)
        if not status:
            return False
        done_values = {item.strip().lower() for item in settings.notion_done_statuses.split(",")}
        status_type = status.get("type")
        value = status.get(status_type) if status_type in {"status", "select"} else {}
        if not isinstance(value, dict):
            return False
        return str(value.get("name", "")).strip().lower() in done_values

    def _property_name(self, properties: dict[str, Any], name: str) -> str | None:
        prop = properties.get(name)
        if not prop:
            return None
        prop_type = prop.get("type")
        if prop_type in {"status", "select"}:
            value = prop.get(prop_type) or {}
            if not isinstance(value, dict):
                return None
            return str(value.get("name") or "").strip() or None
        if prop_type == "multi_select":
            values = [str(item.get("name", "")).strip() for item in prop.get("multi_select", [])]
            return ", ".join(value for value in values if value) or None
        return None
