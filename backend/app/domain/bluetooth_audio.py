from __future__ import annotations

from dataclasses import dataclass
import logging
import os
import re
import shutil
import subprocess
from typing import Literal

logger = logging.getLogger(__name__)

BluetoothStatus = Literal["connected", "disconnected", "unavailable"]


@dataclass(frozen=True)
class BluetoothAudioSnapshot:
    status: BluetoothStatus
    device_name: str | None
    is_default_output: bool


class BluetoothAudioService:
    def __init__(self, *, pulse_server: str | None = None) -> None:
        self._pulse_server = pulse_server if pulse_server is not None else os.environ.get("PULSE_SERVER")

    def snapshot(self) -> BluetoothAudioSnapshot:
        if shutil.which("pactl") is None:
            return BluetoothAudioSnapshot("unavailable", None, False)

        default_sink = self._run(["pactl", "get-default-sink"])
        if default_sink is None:
            return BluetoothAudioSnapshot("unavailable", None, False)
        default_sink = default_sink.strip()

        sinks = self._parse_sinks(self._run(["pactl", "list", "sinks"]) or "")
        bluetooth_sinks = [sink for sink in sinks if sink["name"].startswith("bluez_output.")]
        if not bluetooth_sinks:
            return BluetoothAudioSnapshot("disconnected", None, False)

        default_bluetooth = next((sink for sink in bluetooth_sinks if sink["name"] == default_sink), None)
        active = default_bluetooth or bluetooth_sinks[0]
        return BluetoothAudioSnapshot(
            "connected",
            active["description"],
            default_bluetooth is not None,
        )

    def _run(self, command: list[str]) -> str | None:
        env = os.environ.copy()
        if self._pulse_server:
            env["PULSE_SERVER"] = self._pulse_server
        try:
            result = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                timeout=3,
                env=env,
            )
        except (OSError, subprocess.SubprocessError) as error:
            logger.debug("Bluetooth audio lookup failed: %s", error)
            return None
        return result.stdout

    @staticmethod
    def _parse_sinks(output: str) -> list[dict[str, str]]:
        sinks: list[dict[str, str]] = []
        current: dict[str, str] | None = None
        for line in output.splitlines():
            if line.startswith("Sink #"):
                if current and current.get("name"):
                    sinks.append(current)
                current = {}
                continue
            if current is None:
                continue
            match = re.match(r"\s+(Name|Description):\s+(.*)", line)
            if match:
                current[match.group(1).lower()] = match.group(2).strip()
        if current and current.get("name"):
            sinks.append(current)
        return sinks
