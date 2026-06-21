import re
import subprocess

from app.core.settings import settings


class PiVolumeService:
    """Controls the Raspberry Pi ALSA mixer; no model output reaches the shell."""

    def __init__(self, card: int | None = None, control: str | None = None, step: int | None = None):
        self._card = settings.pi_volume_card if card is None else card
        self._control = settings.pi_volume_control if control is None else control
        self._step = settings.pi_volume_step_percent if step is None else step

    def current(self) -> int:
        result = self._run("sget", self._control)
        match = re.search(r"\[(\d{1,3})%\]", result.stdout)
        if match is None:
            raise RuntimeError("Raspberry Pi volume control is unavailable.")
        return int(match.group(1))

    def adjust(self, direction: str) -> int:
        current = self.current()
        target = max(0, min(100, current + (self._step if direction == "up" else -self._step)))
        return self.set(target)

    def set(self, percent: int) -> int:
        if not 0 <= percent <= 100:
            raise ValueError("Volume must be between 0 and 100 percent.")
        self._run("sset", self._control, f"{percent}%")
        return self.current()

    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
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
