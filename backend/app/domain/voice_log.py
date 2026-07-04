from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.database.models import VoiceCommandLog
from app.database.session import SessionLocal
from app.domain.voice_commands import VoiceCommand


@dataclass(frozen=True)
class VoiceCommandLogEntry:
    id: int
    occurred_at: datetime
    transcript: str | None
    action: str | None
    interpret_source: str | None
    artist: str | None
    volume_percent: int | None
    intent_message: str | None
    status: str
    response_message: str | None
    audio_seconds: float | None
    wake_score: float | None
    failure_stage: str | None


class VoiceLogService:
    def __init__(self, session_factory=SessionLocal) -> None:
        self._session_factory = session_factory

    def record(
        self,
        *,
        transcript: str | None = None,
        command: VoiceCommand | None = None,
        interpret_source: str | None = None,
        status: str,
        response_message: str | None = None,
        audio_seconds: float | None = None,
        wake_score: float | None = None,
        failure_stage: str | None = None,
    ) -> VoiceCommandLogEntry:
        action = command.action if command else None
        artist = command.artist if command else None
        volume_percent = command.volume_percent if command else None
        intent_message = command.message if command else None
        row = VoiceCommandLog(
            occurred_at=datetime.now(UTC),
            transcript=(transcript or "").strip()[:500] or None,
            action=action,
            interpret_source=interpret_source,
            artist=artist[:200] if artist else None,
            volume_percent=volume_percent,
            intent_message=intent_message[:500] if intent_message else None,
            status=status,
            response_message=(response_message or "").strip()[:500] or None,
            audio_seconds=audio_seconds,
            wake_score=wake_score,
            failure_stage=failure_stage,
        )
        with self._session_factory.begin() as session:
            session.add(row)
            session.flush()
            return self._entry(row)

    def recent(self, *, days: int = 30, limit: int = 200) -> list[VoiceCommandLogEntry]:
        since = datetime.now(UTC) - timedelta(days=max(1, days))
        with self._session_factory() as session:
            rows = session.scalars(
                select(VoiceCommandLog)
                .where(VoiceCommandLog.occurred_at >= since)
                .order_by(VoiceCommandLog.occurred_at.desc())
                .limit(max(1, min(limit, 1_000)))
            ).all()
            return [
                self._entry(row)
                for row in rows
            ]

    @staticmethod
    def _entry(row: VoiceCommandLog) -> VoiceCommandLogEntry:
        return VoiceCommandLogEntry(
            id=row.id,
            occurred_at=row.occurred_at,
            transcript=row.transcript,
            action=row.action,
            interpret_source=row.interpret_source,
            artist=row.artist,
            volume_percent=row.volume_percent,
            intent_message=row.intent_message,
            status=row.status,
            response_message=row.response_message,
            audio_seconds=row.audio_seconds,
            wake_score=row.wake_score,
            failure_stage=row.failure_stage,
        )
