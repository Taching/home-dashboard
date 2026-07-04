import os
import re
import subprocess

from app.core.settings import settings


class PiVolumeService:
    """Controls Raspberry Pi output volume via PulseAudio or ALSA."""

    def __init__(self, card: int | None = None, control: str | None = None, step: int | None = None):
        self._card = settings.pi_volume_card if card is None else card
        self._control = settings.pi_volume_control if control is None else control
        self._step = settings.pi_volume_step_percent if step is None else step

    def current(self) -> int:
        if self._prefer_pulse():
            try:
                return self._pulse_current()
            except RuntimeError:
                pass
        return self._alsa_current()

    def adjust(self, direction: str) -> int:
        current = self.current()
        target = max(0, min(100, current + (self._step if direction == "up" else -self._step)))
        return self.set(target)

    def set(self, percent: int) -> int:
        if not 0 <= percent <= 100:
            raise ValueError("Volume must be between 0 and 100 percent.")
        if self._prefer_pulse():
            try:
                self._run_pactl("set-sink-volume", "@DEFAULT_SINK@", f"{percent}%")
                return self._pulse_current()
            except RuntimeError:
                pass
        self._run_amixer("sset", self._control, f"{percent}%")
        return self._alsa_current()

    def output_label(self) -> str:
        if self._prefer_pulse():
            try:
                return self._pulse_output_label()
            except RuntimeError:
                pass
        return "Audio output"

    def _prefer_pulse(self) -> bool:
        return bool(os.environ.get("PULSE_SERVER"))

    def _pulse_current(self) -> int:
        result = self._run_pactl("get-sink-volume", "@DEFAULT_SINK@")
        match = re.search(r"/\s*(\d{1,3})%", result.stdout)
        if match is None:
            raise RuntimeError("Raspberry Pi volume control is unavailable.")
        return int(match.group(1))

    def _pulse_output_label(self) -> str:
        default_sink = self._run_pactl("get-default-sink").stdout.strip()
        listing = self._run_pactl("list", "sinks").stdout
        for block in listing.split("Sink #")[1:]:
            if f"Name: {default_sink}" not in block:
                continue
            match = re.search(r"Description: (.+)", block)
            if match:
                label = match.group(1).strip()
                if label:
                    return label
        return "Audio output"

    def _alsa_current(self) -> int:
        result = self._run_amixer("sget", self._control)
        match = re.search(r"\[(\d{1,3})%\]", result.stdout)
        if match is None:
            raise RuntimeError("Raspberry Pi volume control is unavailable.")
        return int(match.group(1))

    def _run_pactl(self, *args: str) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                ["pactl", *args],
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise RuntimeError("Raspberry Pi volume control is unavailable.") from error

    def _run_amixer(self, *args: str) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                ["amixer", "-c", str(self._card), *args],
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise RuntimeError("Raspberry Pi volume control is unavailable.") from error
