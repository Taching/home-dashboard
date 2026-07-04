from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from websockets.sync.client import connect

from app.core.settings import settings


class OpenClawError(RuntimeError):
    pass


@dataclass(frozen=True)
class OpenClawMessage:
    id: str
    role: str
    text: str
    created_at: str | None = None


class OpenClawService:
    def __init__(self, context_provider: Callable[[], str | None] | None = None) -> None:
        self._last_error: str | None = None
        self._context_provider = context_provider
        self._preferred_session_key: str | None = None
        self._preferred_session_checked_at = 0.0

    def configured(self) -> bool:
        return bool(settings.openclaw_gateway_ws_url and settings.openclaw_gateway_token)

    def status(self) -> str:
        if not self.configured():
            return "not_configured"
        return "unavailable" if self._last_error else "ready"

    def history(self, limit: int = 20) -> list[OpenClawMessage]:
        try:
            payload = self._request(
                "chat.history",
                {"sessionKey": self._session_key(), "limit": limit},
            )
            messages = [self._normalise_message(message) for message in payload.get("messages", [])]
            self._last_error = None
            return [message for message in messages if message.text][-limit:]
        except Exception as error:
            self._last_error = "OpenClaw is unavailable."
            raise OpenClawError(self._last_error) from error

    def send(self, message: str) -> dict[str, str | None]:
        try:
            payload = self._request(
                "chat.send",
                {
                    "message": self._message_with_context(message),
                    "sessionKey": self._session_key(),
                    "deliver": True,
                    "timeoutMs": 30_000,
                    "idempotencyKey": str(uuid4()),
                },
            )
            delivery = self._find_delivery_status(payload)
            if delivery not in {"sent", "suppressed", "accepted", "queued", "started", "running", "completed"}:
                raise OpenClawError("OpenClaw did not accept the message.")
            self._last_error = None
            return {"delivery_status": delivery, "reply": self._find_reply(payload)}
        except OpenClawError:
            self._last_error = "OpenClaw did not accept the message."
            raise
        except Exception as error:
            self._last_error = "OpenClaw is unavailable."
            raise OpenClawError(self._last_error) from error

    def _message_with_context(self, message: str) -> str:
        if self._context_provider is None:
            return message
        try:
            context = self._context_provider()
        except Exception:
            return message
        if not context:
            return message
        return (
            "Use this private dashboard context to answer the user's request. "
            "Do not expose secrets or mention data that is not present here.\n\n"
            f"{context.strip()}\n\n"
            f"User request: {message}"
        )

    def _session_key(self) -> str:
        if not settings.openclaw_prefer_telegram_session:
            return settings.openclaw_session_key
        now = time.time()
        if self._preferred_session_key and now - self._preferred_session_checked_at < 30:
            return self._preferred_session_key
        try:
            payload = self._request("sessions.list", {"limit": 100})
            self._preferred_session_key = self._find_preferred_session_key(payload) or settings.openclaw_session_key
            self._preferred_session_checked_at = now
            return self._preferred_session_key
        except Exception:
            return settings.openclaw_session_key

    def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self.configured():
            raise OpenClawError("OpenClaw is not configured.")
        assert settings.openclaw_gateway_ws_url and settings.openclaw_gateway_token
        with connect(settings.openclaw_gateway_ws_url, open_timeout=5, close_timeout=2) as socket:
            challenge = json.loads(socket.recv())
            nonce = challenge.get("payload", {}).get("nonce")
            if not nonce:
                raise OpenClawError("OpenClaw did not provide a connection challenge.")
            connect_id = str(uuid4())
            socket.send(json.dumps({
                "type": "req", "id": connect_id, "method": "connect",
                "params": {
                    "minProtocol": 4, "maxProtocol": 4,
                    "client": {"id": "openclaw-tui", "displayName": "Chili Dashboard", "version": "0.1.0", "platform": "linux", "mode": "ui"},
                    "role": "operator", "scopes": ["operator.read", "operator.write"],
                    "caps": [], "commands": [], "permissions": {},
                    "auth": {"token": settings.openclaw_gateway_token},
                    "locale": "en-US", "userAgent": "chili-dashboard/0.1.0",
                },
            }))
            self._receive_response(socket, connect_id)
            request_id = str(uuid4())
            socket.send(json.dumps({"type": "req", "id": request_id, "method": method, "params": params}))
            return self._receive_response(socket, request_id)

    @staticmethod
    def _receive_response(socket: Any, request_id: str) -> dict[str, Any]:
        while True:
            frame = json.loads(socket.recv())
            if frame.get("type") != "res" or frame.get("id") != request_id:
                continue
            if not frame.get("ok"):
                error = frame.get("error", {})
                raise OpenClawError(error.get("message", "OpenClaw rejected the request."))
            return frame.get("payload") or {}

    @staticmethod
    def _normalise_message(message: dict[str, Any]) -> OpenClawMessage:
        content = OpenClawService._message_text(message)
        role = str(message.get("role", "assistant"))
        if role == "toolResult":
            content = ""
            role = "assistant"
        elif role not in {"user", "assistant", "system"}:
            role = "assistant"
        created_at = message.get("createdAt", message.get("timestamp"))
        return OpenClawMessage(
            id=str(message.get("id", message.get("messageId", uuid4()))),
            role=role,
            text=str(content).strip(),
            created_at=str(created_at) if created_at is not None else None,
        )

    @staticmethod
    def _message_text(message: dict[str, Any]) -> str:
        content = message.get("content", message.get("text", ""))
        if isinstance(content, str):
            return content
        if isinstance(content, dict):
            return OpenClawService._content_part_text(content)
        if isinstance(content, list):
            parts = [OpenClawService._content_part_text(part) for part in content]
            return "\n".join(part for part in parts if part)
        return str(content)

    @staticmethod
    def _content_part_text(part: Any) -> str:
        if not isinstance(part, dict):
            return str(part)
        if part.get("type") == "toolCall":
            if part.get("name") != "message":
                return ""
            arguments = part.get("arguments") if isinstance(part.get("arguments"), dict) else {}
            input_data = part.get("input") if isinstance(part.get("input"), dict) else {}
            message = arguments.get("message", input_data.get("message", ""))
            return str(message)
        if part.get("type") == "toolResult":
            return ""
        value = part.get("text", part.get("content", ""))
        return value if isinstance(value, str) else ""

    @staticmethod
    def _find_preferred_session_key(payload: dict[str, Any]) -> str | None:
        sessions = payload.get("sessions", [])
        if not isinstance(sessions, list):
            return None
        telegram_sessions = []
        for session in sessions:
            if not isinstance(session, dict):
                continue
            origin = session.get("origin") if isinstance(session.get("origin"), dict) else {}
            delivery = session.get("deliveryContext") if isinstance(session.get("deliveryContext"), dict) else {}
            is_telegram = (
                session.get("lastChannel") == "telegram"
                or origin.get("provider") == "telegram"
                or delivery.get("channel") == "telegram"
            )
            key = session.get("key")
            if is_telegram and isinstance(key, str) and key:
                telegram_sessions.append(session)
        if not telegram_sessions:
            return None
        selected = max(telegram_sessions, key=lambda item: int(item.get("updatedAt") or 0))
        return str(selected["key"])

    @staticmethod
    def _find_delivery_status(payload: dict[str, Any]) -> str | None:
        result = payload.get("result", payload)
        if not isinstance(result, dict):
            return None
        return result.get("deliveryStatus", result.get("delivery_status", result.get("status", "accepted")))

    @staticmethod
    def _find_reply(payload: dict[str, Any]) -> str | None:
        result = payload.get("result", payload)
        if not isinstance(result, dict):
            return None
        value = result.get("reply", result.get("text"))
        return str(value) if value else None
