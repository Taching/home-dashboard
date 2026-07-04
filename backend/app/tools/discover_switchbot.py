"""List SwitchBot devices visible through the Cloud Open API."""

from app.core.settings import settings
from app.domain.switchbot import SwitchBotClient, SwitchBotError


def main() -> None:
    if not settings.switchbot_token or not settings.switchbot_secret:
        raise SystemExit("Set SWITCHBOT_TOKEN and SWITCHBOT_SECRET in .env first.")

    client = SwitchBotClient()
    try:
        devices = client.list_devices()
    except SwitchBotError as error:
        raise SystemExit(str(error)) from error

    if not devices:
        raise SystemExit("No SwitchBot devices returned.")

    print("SwitchBot devices:")
    for device in devices:
        print(
            f"- {device['device_name'] or '(unnamed)'} "
            f"[{device['device_type']}] id={device['device_id']}"
        )


if __name__ == "__main__":
    main()
