# Chili Home Dashboard

A Raspberry Pi 5 kiosk dashboard for room conditions and home controls.

## V1 scope

- Fullscreen React dashboard on HDMI.
- Python/FastAPI control API.
- SHT31 temperature and humidity readings, stored every five minutes.
- BroadLink RM4 Mini light controls.
- Keyboard fallbacks and screen visibility controls.
- Historical 24-hour sensor chart.
- Docker Compose services that restart after boot.

Voice, Calendar, Notion, phone control, remote access, and additional appliances are separate phases. This keeps the first release testable and reliable.

## Apple Calendar bridge

Apple Calendar is available to the dashboard through a small macOS bridge, not directly from the Pi. The bridge reads the calendars already visible in the Mac Calendar app and sends only today's event title and time range to the Pi. See [macos/apple-calendar-bridge/README.md](macos/apple-calendar-bridge/README.md) for setup.

## OpenClaw shared chat

The Ask Chili panel uses the existing OpenClaw main session and mirrors replies to Telegram. On the Pi, add the following to `.env`, using the gateway’s local token:

```env
OPENCLAW_GATEWAY_WS_URL=ws://host.docker.internal:18789
OPENCLAW_GATEWAY_TOKEN=<gateway token>
OPENCLAW_SESSION_KEY=agent:main:main
```

Restart the dashboard with `docker compose up --build -d`. The token is read by the backend only; it is never sent to the browser. The OpenClaw Gateway must accept the dashboard backend as an authenticated local operator client.

## Local development

1. Copy `.env.example` to `.env` and fill only values required for the active phase.
2. Run `docker compose up --build`.
3. Open `http://localhost:8080` on the Pi.

On the Raspberry Pi, include the hardware override:

```sh
docker compose -f compose.yaml -f compose.pi.yaml up --build -d
```

The production dashboard intentionally binds to `127.0.0.1`. Do not expose it to the LAN or internet until Phase 6 authentication is implemented.

## Project layout

- `backend/` — FastAPI, device integrations, scheduling, database.
- `frontend/` — React dashboard, kiosk keyboard controls.
- `voice/` — reserved for the independent wake-word/audio worker.
- `deploy/` — systemd units for Compose and Chromium kiosk startup.
- `docs/` — implementation plan and interface contracts.
- `data/` — persistent SQLite database and learned IR code files; never commit.

## Deployment principle

Docker owns application services. Chromium remains a host-level systemd service because HDMI kiosk display, screen blanking, Bluetooth audio, and desktop-session integration are more reliable outside a browser container.
