from dataclasses import dataclass
import re
from typing import Literal


@dataclass(frozen=True)
class VoiceCommand:
    action: Literal["spotify.play_artist", "spotify.volume_up", "spotify.volume_down"]
    argument: str | None = None


def parse_voice_command(transcript: str) -> VoiceCommand | None:
    text = " ".join(transcript.lower().strip().split())
    artist = re.fullmatch(r"(?:play|start) (?:spotify )?(.+)", text)
    if artist and artist.group(1):
        return VoiceCommand("spotify.play_artist", artist.group(1))
    if text in {"volume up", "increase volume", "turn it up", "make it louder"}:
        return VoiceCommand("spotify.volume_up")
    if text in {"volume down", "decrease volume", "turn it down", "make it quieter"}:
        return VoiceCommand("spotify.volume_down")
    return None
