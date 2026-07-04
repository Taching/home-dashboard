from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import time
import uuid
from typing import Literal

import httpx

from app.core.settings import settings

logger = logging.getLogger(__name__)

SwitchBotPowerCommand = Literal["turnOn", "turnOff"]


class SwitchBotError(RuntimeError):
    pass


class SwitchBotClient:
    API_BASE = "https://api.switch-bot.com/v1.1"

    def __init__(
        self,
        *,
        token: str | None = None,
        secret: str | None = None,
        device_id: str | None = None,
    ) -> None:
        self._token = token if token is not None else settings.switchbot_token
        self._secret = secret if secret is not None else settings.switchbot_secret
        self._device_id = device_id if device_id is not None else settings.switchbot_plug_device_id

    @property
    def configured(self) -> bool:
        return bool(self._token and self._secret and self._device_id)

    @property
    def credentials_configured(self) -> bool:
        return bool(self._token and self._secret)

    def list_devices(self) -> list[dict[str, str]]:
        if not self.credentials_configured:
            raise SwitchBotError("SwitchBot token and secret are required.")
        payload = self._request("GET", "/devices")
        body = payload.get("body") or {}
        devices = body.get("deviceList") or []
        return [
            {
                "device_id": device["deviceId"],
                "device_name": device.get("deviceName", ""),
                "device_type": device.get("deviceType", ""),
            }
            for device in devices
            if isinstance(device, dict) and device.get("deviceId")
        ]

    def set_power(self, on: bool) -> None:
        if not self.configured:
            raise SwitchBotError("SwitchBot is not configured.")
        command: SwitchBotPowerCommand = "turnOn" if on else "turnOff"
        payload = self._request(
            "POST",
            f"/devices/{self._device_id}/commands",
            json={"command": command, "parameter": "default", "commandType": "command"},
        )
        if payload.get("statusCode") != 100:
            message = payload.get("message") or "SwitchBot command failed."
            raise SwitchBotError(message)

    def _request(self, method: str, path: str, json: dict | None = None) -> dict:
        if not self._token or not self._secret:
            raise SwitchBotError("SwitchBot token and secret are required.")

        timestamp = str(int(round(time.time() * 1000)))
        nonce = str(uuid.uuid4())
        signature = base64.b64encode(
            hmac.new(
                self._secret.encode("utf-8"),
                f"{self._token}{timestamp}{nonce}".encode("utf-8"),
                digestmod=hashlib.sha256,
            ).digest()
        ).decode("utf-8")
        headers = {
            "Authorization": self._token,
            "sign": signature,
            "t": timestamp,
            "nonce": nonce,
            "Content-Type": "application/json",
        }
        try:
            response = httpx.request(
                method,
                f"{self.API_BASE}{path}",
                headers=headers,
                json=json,
                timeout=15,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as error:
            logger.debug("SwitchBot request failed: %s", error)
            raise SwitchBotError("SwitchBot request failed.") from error
        return payload if isinstance(payload, dict) else {}
