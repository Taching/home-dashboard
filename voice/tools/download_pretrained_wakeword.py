"""Download an official openWakeWord model for benchmarking."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import openwakeword
from openwakeword.utils import download_file


def main() -> int:
    parser = argparse.ArgumentParser(description="Download a pre-trained openWakeWord .tflite model.")
    parser.add_argument(
        "name",
        choices=sorted(openwakeword.MODELS.keys()),
        help="Model name (e.g. hey_jarvis)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("/models"),
        help="Directory to save the model (default: /models in the voice container)",
    )
    args = parser.parse_args()

    info = openwakeword.MODELS[args.name]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    download_file(info["download_url"], str(args.output_dir))
    filename = info["download_url"].rsplit("/", 1)[-1]
    destination = args.output_dir / filename
    print(destination)
    return 0


if __name__ == "__main__":
    sys.exit(main())
