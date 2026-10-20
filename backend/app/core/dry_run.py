"""Dry-run guard for external side effects.

When production_mode is False (the default), external writes and device control
are blocked and logged. This protects fresh checkouts, CI, and agent environments.

Usage:
    from app.core.dry_run import guard_external_call, is_dry_run

    if is_dry_run():
        guard_external_call("Telegram", f"notify_user({message!r})")
        return {"delivery_status": "dry_run", "reply": None}
"""

from __future__ import annotations

import logging

from app.core.settings import settings

logger = logging.getLogger(__name__)


def is_dry_run() -> bool:
    """Return True if production_mode is disabled (external calls blocked)."""
    return not settings.production_mode


def guard_external_call(service: str, description: str) -> None:
    """Log a blocked external call in dry-run mode."""
    logger.info("[DRY-RUN] %s: %s", service, description)
