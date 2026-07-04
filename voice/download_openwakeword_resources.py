"""Download openWakeWord shared runtime models into the installed package."""

import os

import openwakeword
from openwakeword.utils import download_file


def download_once(url: str, target: str) -> None:
    filename = url.rsplit("/", 1)[-1]
    if not os.path.exists(os.path.join(target, filename)):
        download_file(url, target)


def main() -> None:
    target = os.path.join(os.path.dirname(openwakeword.__file__), "resources", "models")
    os.makedirs(target, exist_ok=True)

    for model in openwakeword.FEATURE_MODELS.values():
        download_once(model["download_url"], target)
        download_once(model["download_url"].replace(".tflite", ".onnx"), target)

    for model in openwakeword.VAD_MODELS.values():
        download_once(model["download_url"], target)


if __name__ == "__main__":
    main()
