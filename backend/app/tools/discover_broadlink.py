"""Discover BroadLink devices visible from the Pi's local network."""


def main() -> None:
    import broadlink

    devices = broadlink.discover(timeout=10)
    if not devices:
        raise SystemExit("No BroadLink devices found. Check the Pi and RM4 Mini are on the same LAN.")

    for device in devices:
        host, _ = device.host
        mac = ":".join(f"{byte:02X}" for byte in device.mac)
        print(
            f"model={device.model or 'unknown'} "
            f"host={host} mac={mac} device_type={device.devtype} "
            f"device_type_hex=0x{device.devtype:04X}"
        )


if __name__ == "__main__":
    main()
