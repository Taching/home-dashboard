"""Local wake-word listener that forwards only post-wake commands for transcription."""

import logging
import os
import subprocess
import tempfile
import time
import wave
from pathlib import Path

import httpx
import numpy as np
from openwakeword.model import Model
from wakeword import WakeWordGate

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger("voice")

SAMPLE_RATE = 16_000
SAMPLE_WIDTH = 2
CHANNELS = 1
COMMAND_SECONDS = float(os.environ.get("VOICE_COMMAND_MAX_SECONDS", "5"))
COMMAND_MIN_SECONDS = float(os.environ.get("VOICE_COMMAND_MIN_SECONDS", "1.0"))
COMMAND_SILENCE_SECONDS = float(os.environ.get("VOICE_COMMAND_SILENCE_SECONDS", "0.8"))
SILENCE_RMS_THRESHOLD = float(os.environ.get("VOICE_SILENCE_RMS_THRESHOLD", "380"))
COOLDOWN_SECONDS = float(os.environ.get("VOICE_COOLDOWN_SECONDS", "1.5"))
POST_WAKE_SKIP_SECONDS = float(os.environ.get("VOICE_POST_WAKE_SKIP_SECONDS", "0.3"))
WAKEWORD_REARM_SECONDS = float(os.environ.get("VOICE_WAKEWORD_REARM_SECONDS", "0.5"))
# openWakeWord consumes 80 ms frames at 16 kHz.
WAKEWORD_FRAME_SAMPLES = 1_280


def required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} must be configured")
    return value


def start_capture(device: str) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [
            "arecord",
            "--device", device,
            "--format", "S16_LE",
            "--rate", str(SAMPLE_RATE),
            "--channels", str(CHANNELS),
            "--file-type", "raw",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def read_exact(stream, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = stream.read(remaining)
        if not chunk:
            raise RuntimeError("ALSA capture stream ended")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def record_command(stream) -> bytes:
    frames: list[bytes] = []
    max_frames = round(COMMAND_SECONDS * SAMPLE_RATE / WAKEWORD_FRAME_SAMPLES)
    min_frames = round(COMMAND_MIN_SECONDS * SAMPLE_RATE / WAKEWORD_FRAME_SAMPLES)
    silence_frames_needed = round(COMMAND_SILENCE_SECONDS * SAMPLE_RATE / WAKEWORD_FRAME_SAMPLES)
    silent_frames = 0
    heard_speech = False

    for _ in range(max_frames):
        frame = read_exact(stream, WAKEWORD_FRAME_SAMPLES * SAMPLE_WIDTH)
        frames.append(frame)
        samples = np.frombuffer(frame, dtype=np.int16).astype(np.float32)
        rms = float(np.sqrt(np.mean(samples * samples)))
        if rms >= SILENCE_RMS_THRESHOLD:
            heard_speech = True
            silent_frames = 0
        elif heard_speech:
            silent_frames += 1
            if len(frames) >= min_frames and silent_frames >= silence_frames_needed:
                break

    return b"".join(frames)


def write_wav(audio: bytes) -> Path:
    handle = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    path = Path(handle.name)
    handle.close()
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(CHANNELS)
        wav.setsampwidth(SAMPLE_WIDTH)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(audio)
    return path


def transcribe(audio: bytes, api_key: str, model: str) -> str:
    path = write_wav(audio)
    try:
        with path.open("rb") as recording, httpx.Client(timeout=45) as client:
            response = client.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {api_key}"},
                data={"model": model},
                files={"file": ("command.wav", recording, "audio/wav")},
            )
        response.raise_for_status()
        return str(response.json().get("text", "")).strip()
    finally:
        path.unlink(missing_ok=True)


def dispatch(transcript: str, backend_url: str) -> dict[str, str]:
    with httpx.Client(timeout=20) as client:
        response = client.post(f"{backend_url}/api/v1/voice/transcripts", json={"text": transcript})
    response.raise_for_status()
    return response.json()


def update_status(
    state: str,
    backend_url: str,
    transcript: str | None = None,
    message: str | None = None,
) -> bool:
    try:
        with httpx.Client(timeout=5) as client:
            client.post(
                f"{backend_url}/api/v1/voice/status",
                json={"state": state, "transcript": transcript, "message": message},
            ).raise_for_status()
        return True
    except httpx.HTTPError:
        logger.warning("Could not update dashboard voice status")
        return False


def report_failure(backend_url: str, message: str, transcript: str | None = None) -> None:
    """Publish a short, user-safe failure without stopping the listener."""
    update_status("error", backend_url, transcript, message[:200])


def main() -> None:
    api_key = required("OPENAI_API_KEY")
    device = os.environ.get("VOICE_AUDIO_DEVICE", os.environ.get("AUDIO_DEVICE", "plughw:2,0"))
    wakeword_model = os.environ.get("VOICE_WAKEWORD_MODEL", "/models/hey_chili.tflite")
    wakeword_label = os.environ.get("VOICE_WAKEWORD_LABEL", "Hey Chili")
    backend_url = os.environ.get("BACKEND_URL", "http://backend:8000").rstrip("/")
    threshold = float(os.environ.get("VOICE_WAKEWORD_THRESHOLD", "0.4"))
    rearm_seconds = float(os.environ.get("VOICE_WAKEWORD_REARM_SECONDS", str(WAKEWORD_REARM_SECONDS)))
    transcription_model = os.environ.get("OPENAI_TRANSCRIPTION_MODEL", "gpt-4o-mini-transcribe")
    detector = Model(wakeword_models=[wakeword_model], inference_framework="tflite")
    capture = start_capture(device)
    assert capture.stdout is not None
    gate = WakeWordGate(threshold, rearm_seconds, COOLDOWN_SECONDS)
    frame_bytes = WAKEWORD_FRAME_SAMPLES * SAMPLE_WIDTH
    while not update_status("idle", backend_url):
        time.sleep(1)
    logger.info("Listening on %s for %s", device, wakeword_label)

    try:
        while True:
            frame = read_exact(capture.stdout, frame_bytes)
            scores = detector.predict(np.frombuffer(frame, dtype=np.int16))
            score = max(scores.values(), default=0.0)

            if not gate.observe(score, time.monotonic()):
                continue

            logger.info("Wake word detected (score %.2f); recording command", score)
            transcript: str | None = None
            stage = "recording"
            try:
                update_status("listening", backend_url)
                skip_frames = round(POST_WAKE_SKIP_SECONDS * SAMPLE_RATE / WAKEWORD_FRAME_SAMPLES)
                for _ in range(skip_frames):
                    read_exact(capture.stdout, frame_bytes)
                audio = record_command(capture.stdout)
                stage = "transcription"
                update_status("thinking", backend_url)
                transcript = transcribe(audio, api_key, transcription_model)
                if not transcript:
                    logger.info("No speech transcribed after wake word")
                    report_failure(backend_url, "I didn't hear a command.")
                    continue

                stage = "command dispatch"
                update_status("thinking", backend_url, transcript)
                result = dispatch(transcript, backend_url)
                status = result.get("status", "failed")
                message = result.get("message") or "The voice command could not complete."
                logger.info("Command dispatched: %s", status)
                update_status("complete" if status == "success" else "error", backend_url, transcript, message)
            except httpx.TimeoutException:
                logger.warning("Voice %s timed out", stage)
                report_failure(backend_url, f"Voice {stage} timed out. Please try again.", transcript)
            except httpx.HTTPError:
                logger.exception("Voice %s request failed", stage)
                report_failure(backend_url, f"Voice {stage} failed. Please try again.", transcript)
            except Exception:
                logger.exception("Voice %s failed", stage)
                report_failure(backend_url, "The voice command could not complete.", transcript)
    finally:
        capture.terminate()
        try:
            capture.wait(timeout=5)
        except subprocess.TimeoutExpired:
            capture.kill()


if __name__ == "__main__":
    main()
