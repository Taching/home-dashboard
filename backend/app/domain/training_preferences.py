from __future__ import annotations

from datetime import UTC, datetime

from app.database.models import TrainingPreference
from app.database.session import SessionLocal

MAX_NOTES_LENGTH = 2000


class TrainingPreferencesService:
    def __init__(self, session_factory=SessionLocal) -> None:
        self._session_factory = session_factory

    def get(self) -> dict:
        with self._session_factory() as session:
            row = session.get(TrainingPreference, 1)
            if row is None:
                return {"notes": None, "updated_at": None}
            return {"notes": row.notes, "updated_at": row.updated_at.isoformat()}

    def save(self, notes: str | None) -> dict:
        cleaned = (notes or "").strip()[:MAX_NOTES_LENGTH] or None
        now = datetime.now(UTC)
        with self._session_factory() as session:
            row = session.get(TrainingPreference, 1)
            if row is None:
                row = TrainingPreference(id=1, notes=cleaned, updated_at=now)
                session.add(row)
            else:
                row.notes = cleaned
                row.updated_at = now
            session.commit()
        return self.get()

    def prompt_snippet(self) -> str:
        """A short block to append to coach/replan prompts, or '' if none set.

        Advice-flavor only. Never wire this into CalendarAdjuster._apply,
        policy.py, constraints.py, ranker.py, or scheduler.py — preferences
        must never gate the deterministic scheduler.
        """
        notes = (self.get().get("notes") or "").strip()
        if not notes:
            return ""
        return f"Toshi's training preferences (context only, never a scheduling rule):\n{notes}"
