"""Print live wake-word scores for one or more .tflite models."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

import numpy as np
from openwakeword.model import Model

SAMPLE_RATE = 16_000
FRAME_SAMPLES = 1_280
SAMPLE_WIDTH = 2


def read_exact(stream, nbytes: int) -> bytes:
    data = b""
    while len(data) < nbytes:
        chunk = stream.read(nbytes - len(data))
        if not chunk:
            raise RuntimeError("Audio stream ended unexpectedly")
        data += chunk
    return data


def start_capture(device: str) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        ["arecord", "-D", device, "-f", "S16_LE", "-r", str(SAMPLE_RATE), "-c", "1", "-q"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Stream wake-word scores from the USB mic.")
    parser.add_argument("models", nargs="+", help="Paths to .tflite wake-word models")
    parser.add_argument("--device", default=os.environ.get("VOICE_AUDIO_DEVICE", "plughw:2,0"))
    parser.add_argument("--threshold", type=float, default=0.30)
    parser.add_argument("--print-every", type=float, default=0.25, help="Seconds between score lines")
    args = parser.parse_args()

    detectors = {
        path: Model(wakeword_models=[path], inference_framework="tflite")
        for path in args.models
    }
    capture = start_capture(args.device)
    assert capture.stdout is not None
    frame_bytes = FRAME_SAMPLES * SAMPLE_WIDTH
    names = [os.path.basename(path) for path in args.models]

    print(f"Listening on {args.device}. Threshold hint: {args.threshold:.2f}")
    print("Say each wake phrase and watch peaks. Ctrl+C to stop.\n")

    last_print = 0.0
    try:
        while True:
            frame = read_exact(capture.stdout, frame_bytes)
            audio = np.frombuffer(frame, dtype=np.int16)
            parts: list[str] = []
            for path, detector in detectors.items():
                scores = detector.predict(audio)
                score = float(max(scores.values(), default=0.0))
                label = os.path.basename(path)
                marker = "*" if score >= args.threshold else " "
                parts.append(f"{marker}{label}={score:.3f}")
            now = time.monotonic()
            if now - last_print >= args.print_every:
                print("  ".join(parts))
                last_print = now
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        capture.terminate()
        capture.wait(timeout=3)
    return 0


if __name__ == "__main__":
    sys.exit(main())
