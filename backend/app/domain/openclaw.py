from __future__ import annotations

import json
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
    def __init__(self) -> None:
        self._last_error: str | None = None

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
                {"sessionKey": settings.openclaw_session_key, "limit": limit},
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
                "agent",
                {
                    "message": message,
                    "sessionKey": settings.openclaw_session_key,
                    "deliver": True,
                    "bestEffortDeliver": False,
                    "timeout": 30,
                    "idempotencyKey": str(uuid4()),
                },
            )
            delivery = self._find_delivery_status(payload)
            if delivery not in {"sent", "suppressed"}:
                raise OpenClawError("Telegram delivery was not confirmed.")
            self._last_error = None
            return {"delivery_status": delivery, "reply": self._find_reply(payload)}
        except OpenClawError:
            self._last_error = "Telegram delivery was not confirmed."
            raise
        except Exception as error:
            self._last_error = "OpenClaw is unavailable."
            raise OpenClawError(self._last_error) from error

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
                    "client": {"id": "chili-dashboard", "version": "0.1.0", "platform": "linux", "mode": "operator"},
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
        content = message.get("content", message.get("text", ""))
        if isinstance(content, list):
            content = "\n".join(
                part.get("text", "") if isinstance(part, dict) else str(part) for part in content
            )
        if isinstance(content, dict):
            content = content.get("text", "")
        role = str(message.get("role", "assistant"))
        if role not in {"user", "assistant", "system"}:
            role = "assistant"
        created_at = message.get("createdAt", message.get("timestamp"))
        return OpenClawMessage(
            id=str(message.get("id", message.get("messageId", uuid4()))),
            role=role,
            text=str(content).strip(),
            created_at=str(created_at) if created_at is not None else None,
        )

    @staticmethod
    def _find_delivery_status(payload: dict[str, Any]) -> str | None:
        result = payload.get("result", payload)
        return result.get("deliveryStatus", result.get("delivery_status")) if isinstance(result, dict) else None

    @staticmethod
    def _find_reply(payload: dict[str, Any]) -> str | None:
        result = payload.get("result", payload)
        if not isinstance(result, dict):
            return None
        value = result.get("reply", result.get("text"))
        return str(value) if value else None
