from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

from websockets.sync.client import connect

from app.core.settings import settings
from app.domain.json_types import JsonDict, JsonValue, as_dict, as_list


class OpenClawError(RuntimeError):
    pass


@dataclass(frozen=True)
class OpenClawMessage:
    id: str
    role: str
    text: str
    created_at: str | None = None


class WebSocketConnection(Protocol):
    def recv(self) -> str | bytes:
        ...

    def send(self, message: str | bytes) -> None:
        ...


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
            messages = [
                self._normalise_message(message)
                for message in as_list(payload.get("messages"))
                if isinstance(message, dict)
            ]
            messages = [message for message in messages if message.text]
            messages = self._dedupe_messages(messages)
            self._last_error = None
            return messages[-limit:]
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

    def _request(self, method: str, params: JsonDict) -> JsonDict:
        if not self.configured():
            raise OpenClawError("OpenClaw is not configured.")
        assert settings.openclaw_gateway_ws_url and settings.openclaw_gateway_token
        with connect(settings.openclaw_gateway_ws_url, open_timeout=5, close_timeout=2) as socket:
            challenge = self._json_object(socket.recv())
            nonce = as_dict(challenge.get("payload")).get("nonce")
            if not isinstance(nonce, str) or not nonce:
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
    def _receive_response(socket: WebSocketConnection, request_id: str) -> JsonDict:
        while True:
            frame = OpenClawService._json_object(socket.recv())
            if frame.get("type") != "res" or frame.get("id") != request_id:
                continue
            if not frame.get("ok"):
                message = as_dict(frame.get("error")).get("message")
                raise OpenClawError(str(message or "OpenClaw rejected the request."))
            return as_dict(frame.get("payload"))

    @staticmethod
    def _json_object(raw: str | bytes) -> JsonDict:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _normalise_message(message: JsonDict) -> OpenClawMessage:
        content = OpenClawService._message_text(message)
        role = str(message.get("role", "assistant"))
        if role == "toolResult":
            content = ""
            role = "assistant"
        elif role not in {"user", "assistant", "system"}:
            role = "assistant"
        created_at = message.get("createdAt", message.get("timestamp"))
        text = OpenClawService._display_text(str(content).strip(), role)
        message_id = message.get("id", message.get("messageId"))
        return OpenClawMessage(
            id=str(message_id if message_id is not None else uuid4()),
            role=role,
            text=text,
            created_at=str(created_at) if created_at is not None else None,
        )

    @staticmethod
    def _display_text(text: str, role: str) -> str:
        if role != "user" or not text.startswith("Use this private dashboard context"):
            return text
        marker = "User request: "
        if marker in text:
            return text.split(marker, 1)[1].strip()
        return text

    @staticmethod
    def _dedupe_messages(messages: list[OpenClawMessage]) -> list[OpenClawMessage]:
        deduped: list[OpenClawMessage] = []
        seen: set[tuple[str, str]] = set()
        for message in messages:
            key = (message.role, message.text)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(message)
        return deduped

    @staticmethod
    def _message_text(message: JsonDict) -> str:
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
    def _content_part_text(part: JsonValue) -> str:
        if not isinstance(part, dict):
            return str(part)
        if part.get("type") == "toolCall":
            if part.get("name") != "message":
                return ""
            arguments = as_dict(part.get("arguments"))
            input_data = as_dict(part.get("input"))
            message = arguments.get("message", input_data.get("message", ""))
            return str(message)
        if part.get("type") == "toolResult":
            return ""
        value = part.get("text", part.get("content", ""))
        return value if isinstance(value, str) else ""

    @staticmethod
    def _find_preferred_session_key(payload: JsonDict) -> str | None:
        telegram_sessions: list[JsonDict] = []
        for session in as_list(payload.get("sessions")):
            if not isinstance(session, dict):
                continue
            origin = as_dict(session.get("origin"))
            delivery = as_dict(session.get("deliveryContext"))
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
        selected = max(telegram_sessions, key=lambda item: OpenClawService._integer_value(item.get("updatedAt")))
        return str(selected["key"])

    @staticmethod
    def _integer_value(value: JsonValue | None) -> int:
        if isinstance(value, bool) or value is None:
            return 0
        if isinstance(value, int | float | str):
            try:
                return int(value)
            except ValueError:
                return 0
        return 0

    @staticmethod
    def _find_delivery_status(payload: JsonDict) -> str | None:
        result = as_dict(payload.get("result")) or payload
        value = result.get("deliveryStatus", result.get("delivery_status", result.get("status", "accepted")))
        return str(value) if value else None

    @staticmethod
    def _find_reply(payload: JsonDict) -> str | None:
        result = as_dict(payload.get("result")) or payload
        value = result.get("reply", result.get("text"))
        return str(value) if value else None
