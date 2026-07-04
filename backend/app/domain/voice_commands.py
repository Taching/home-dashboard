"""Constrained AI interpretation for the locally allowlisted voice commands."""

from dataclasses import dataclass
import json
import re
from typing import Literal

import httpx

from app.core.settings import settings

VoiceAction = Literal[
    "spotify.play_artist", "spotify.pause", "system.volume_up", "system.volume_down",
    "system.volume_set", "light.turn_on", "light.turn_off", "openclaw.send_message", "no_match",
]

VOICE_COMMANDS = [
    {"id": "spotify.play_artist", "label": "Play or change artist", "examples": ["play Spotify Yuuri", "change artist to YOASOBI"]},
    {"id": "spotify.pause", "label": "Stop music", "examples": ["stop the music", "pause Spotify"]},
    {"id": "system.volume_up", "label": "Increase Pi volume", "examples": ["turn it up", "make it louder"]},
    {"id": "system.volume_down", "label": "Decrease Pi volume", "examples": ["lower volume", "make it quieter"]},
    {"id": "system.volume_set", "label": "Set Pi volume", "examples": ["set volume to 50 percent"]},
    {"id": "light.turn_on", "label": "Turn lights on", "examples": ["turn on the lights"]},
    {"id": "light.turn_off", "label": "Turn lights off", "examples": ["turn off the lights"]},
    {"id": "openclaw.send_message", "label": "Send a message to Chili", "examples": ["ask Chili what's on my calendar", "tell OpenClaw to summarize today"]},
]

_ACTIONS = {item["id"] for item in VOICE_COMMANDS} | {"no_match"}
_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": sorted(_ACTIONS)},
        "artist": {"type": ["string", "null"]},
        "volume_percent": {"type": ["integer", "null"]},
        "message": {"type": ["string", "null"]},
    },
    "required": ["action", "artist", "volume_percent", "message"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class VoiceCommand:
    action: VoiceAction
    artist: str | None = None
    volume_percent: int | None = None
    message: str | None = None


_SIMPLE_COMMANDS = (
    (re.compile(r"^(?:pause|stop)(?:\s+(?:the\s+)?music|\s+spotify)?\.?$", re.I), "spotify.pause"),
    (re.compile(r"^(?:turn|switch)\s+on(?:\s+the\s+)?lights?\.?$", re.I), "light.turn_on"),
    (re.compile(r"^(?:turn|switch)\s+off(?:\s+the\s+)?lights?\.?$", re.I), "light.turn_off"),
    (re.compile(r"^(?:volume\s+up|turn\s+it\s+up|louder|make\s+it\s+louder)\.?$", re.I), "system.volume_up"),
    (re.compile(r"^(?:volume\s+down|turn\s+it\s+down|quieter|make\s+it\s+quieter|lower(?:\s+the\s+)?volume)\.?$", re.I), "system.volume_down"),
)
_VOLUME_SET = re.compile(r"^set\s+volume\s+to\s+(\d{1,3})\s*(?:percent|%)?\.?$", re.I)
_PLAY_ARTIST = re.compile(r"^play(?:\s+spotify)?\s+(.+)$", re.I)


def match_voice_command_fast_path(transcript: str) -> VoiceCommand | None:
    text = transcript.strip()
    if not text:
        return None
    for pattern, action in _SIMPLE_COMMANDS:
        if pattern.fullmatch(text):
            return VoiceCommand(action)
    volume_match = _VOLUME_SET.fullmatch(text)
    if volume_match:
        return VoiceCommandInterpreter._validate({
            "action": "system.volume_set",
            "artist": None,
            "volume_percent": int(volume_match.group(1)),
            "message": None,
        })
    artist_match = _PLAY_ARTIST.fullmatch(text)
    if artist_match:
        return VoiceCommandInterpreter._validate({
            "action": "spotify.play_artist",
            "artist": artist_match.group(1).strip(),
            "volume_percent": None,
            "message": None,
        })
    return None


class VoiceCommandInterpreter:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        self._api_key = api_key if api_key is not None else settings.openai_api_key
        self._model = model if model is not None else settings.voice_command_model

    def interpret(self, transcript: str) -> VoiceCommand:
        fast_path = match_voice_command_fast_path(transcript)
        if fast_path is not None:
            return fast_path
        if not self._api_key:
            raise RuntimeError("Voice command interpretation is not configured.")
        response = httpx.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
            json={
                "model": self._model,
                "store": False,
                "input": [
                    {"role": "system", "content": "Classify the user's voice command into the supplied schema. Use no_match unless it clearly maps to one allowed action. Volume always means Raspberry Pi OS volume, never Spotify volume. Use openclaw.send_message only when the user asks to ask, tell, message, or send something to Chili/OpenClaw; put only the message content for Chili/OpenClaw in message."},
                    {"role": "user", "content": transcript},
                ],
                "text": {"format": {"type": "json_schema", "name": "voice_command", "strict": True, "schema": _SCHEMA}},
            },
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        raw = payload.get("output_text") or self._output_text(payload)
        return self._validate(json.loads(raw))

    @staticmethod
    def _output_text(payload: dict) -> str:
        for output in payload.get("output", []):
            for content in output.get("content", []):
                if content.get("type") == "output_text":
                    return str(content.get("text", ""))
        raise ValueError("Voice command model returned no text.")

    @staticmethod
    def _validate(payload: object) -> VoiceCommand:
        if not isinstance(payload, dict) or payload.get("action") not in _ACTIONS:
            return VoiceCommand("no_match")
        action = payload["action"]
        artist = payload.get("artist")
        volume = payload.get("volume_percent")
        message = payload.get("message")
        if action == "spotify.play_artist" and isinstance(artist, str) and artist.strip():
            return VoiceCommand(action, artist=artist.strip())
        if action == "system.volume_set" and isinstance(volume, int) and 0 <= volume <= 100:
            return VoiceCommand(action, volume_percent=volume)
        if action == "openclaw.send_message" and isinstance(message, str) and message.strip():
            return VoiceCommand(action, message=message.strip())
        if action in {"spotify.pause", "system.volume_up", "system.volume_down", "light.turn_on", "light.turn_off", "no_match"}:
            return VoiceCommand(action)
        return VoiceCommand("no_match")
