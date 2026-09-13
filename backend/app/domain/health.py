from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class HealthDetail:
    id: str
    label: str
    status: str
    severity: str
    needs_attention: bool
    reason: str
    recommended_action: str | None = None
    observed_at: datetime | None = None

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def dashboard_health_details(
    *,
    calendar_status: str,
    calendar_synced_at: datetime | None,
    walkingpad_status: str,
    walkingpad_synced_at: datetime | None,
    now: datetime | None = None,
) -> list[HealthDetail]:
    current = _as_utc(now or datetime.now(UTC))
    calendar_synced_at = _optional_utc(calendar_synced_at)
    walkingpad_synced_at = _optional_utc(walkingpad_synced_at)

    if calendar_status == "ready":
        calendar = HealthDetail(
            "calendar", "Calendar bridge", "ready", "healthy", False,
            "The Mac calendar publisher is syncing.", observed_at=calendar_synced_at,
        )
    elif calendar_status == "stale":
        calendar = HealthDetail(
            "calendar", "Calendar bridge", "stale", "attention", True,
            "Cached events are visible, but the Mac publisher has stopped updating them.",
            "Check that the Mac is awake and its calendar publisher is running.",
            calendar_synced_at,
        )
    elif calendar_status == "not_configured":
        calendar = HealthDetail(
            "calendar", "Calendar bridge", "not_configured", "info", False,
            "Apple Calendar sync is optional and is not configured.", observed_at=calendar_synced_at,
        )
    else:
        calendar = HealthDetail(
            "calendar", "Calendar bridge", calendar_status, "attention", True,
            "Calendar data is unavailable.",
            "Check the Mac calendar publisher and bridge connection.",
            calendar_synced_at,
        )

    if walkingpad_status == "walking":
        walkingpad = HealthDetail(
            "walkingpad", "WalkingPad", "walking", "healthy", False,
            "A walking session is active.", observed_at=walkingpad_synced_at,
        )
    elif walkingpad_status == "ready":
        walkingpad = HealthDetail(
            "walkingpad", "WalkingPad", "ready", "healthy", False,
            "The collector is ready; the pad may be idle.", observed_at=walkingpad_synced_at,
        )
    elif walkingpad_status == "not_configured":
        walkingpad = HealthDetail(
            "walkingpad", "WalkingPad", "not_configured", "info", False,
            "WalkingPad tracking is optional and is not configured.", observed_at=walkingpad_synced_at,
        )
    else:
        walkingpad = HealthDetail(
            "walkingpad", "WalkingPad", walkingpad_status, "info", False,
            "The pad is off, idle, or outside Bluetooth range; this is normal when unused.",
            "Turn on the WalkingPad only when you want to use it.",
            walkingpad_synced_at,
        )

    return [calendar, walkingpad]


def _optional_utc(value: datetime | None) -> datetime | None:
    return _as_utc(value) if value is not None else None


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
