"""Learn and persist RM4 Mini IR packets for the dashboard light.

Run inside the backend container after BROADLINK_HOST and BROADLINK_MAC are
configured. The command intentionally stores packets only in /data, which is
mounted from the untracked data directory on the Pi.
"""

import base64
import json
import struct
import time
from pathlib import Path

from app.core.settings import settings
from app.domain.lights import BroadlinkRM4MiniAdapter


def learn(label: str) -> bytes:
    adapter = BroadlinkRM4MiniAdapter()
    device = adapter._connect()  # This setup command needs the authenticated device.
    print(f"Press the light remote's {label.upper()} button, then wait...")
    device.enter_learning()
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        time.sleep(1)
        try:
            packet = device.check_data()
        except Exception as error:
            # Some RM4 Mini firmware reports its finite learning storage as full
            # even though it returns the just-captured packet. The upstream
            # library raises before exposing that payload. Read the packet using
            # the RM4 wire format, but only for that specific firmware error.
            if type(error).__name__ == "ReadError":
                continue
            if type(error).__name__ != "StorageError":
                raise
            packet = _check_data_despite_full_storage(device)
        if packet:
            return packet
    raise TimeoutError(f"No {label.upper()} IR packet received within 30 seconds")


def _check_data_despite_full_storage(device) -> bytes:
    packet = struct.pack("<HI", 4, 0x4)
    response = device.send_packet(0x6A, packet)
    payload = device.decrypt(response[0x38:])
    length = struct.unpack("<H", payload[:2])[0]
    return payload[6 : length + 2]


def main() -> None:
    if not settings.broadlink_host or not settings.broadlink_mac:
        raise SystemExit("Set BROADLINK_HOST and BROADLINK_MAC in .env first.")

    on = learn("on")
    off = learn("off")
    destination = Path(settings.broadlink_codes_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(
            {
                "on": base64.b64encode(on).decode(),
                "off": base64.b64encode(off).decode(),
            },
            indent=2,
        )
        + "\n"
    )
    print(f"Saved RM4 Mini packets to {destination}.")


if __name__ == "__main__":
    main()
