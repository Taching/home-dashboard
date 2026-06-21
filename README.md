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

Voice, Notion, phone control, remote access, and additional appliances are separate phases. This keeps the first release testable and reliable.

## Apple Calendar bridge

Apple Calendar is available through a read-only macOS bridge. The dashboard already has the bridge token configured; complete the Mac authorization before starting the bridge service.

1. On the Pi, set `CALENDAR_BRIDGE_BIND_ADDRESS=0.0.0.0` in `.env`, then start the bridge:

   ```sh
   docker compose -f compose.yaml -f compose.pi.yaml -f compose.apple-calendar-bridge.yaml up --build -d
   ```

2. On the Mac that contains the calendars, build and authorize the bundled helper, then install its LaunchAgent for five-minute syncs. macOS must grant **Calendar Full Access** and the Mac must remain logged in. Follow the exact commands in [macos/apple-calendar-bridge/README.md](macos/apple-calendar-bridge/README.md).

## OpenClaw shared chat

The Ask Chili panel uses the existing OpenClaw main session and mirrors replies to Telegram. On the Pi, add the following to `.env`, using the gateway’s local token:

```env
OPENCLAW_GATEWAY_WS_URL=ws://host.docker.internal:18789
OPENCLAW_GATEWAY_TOKEN=<gateway token>
OPENCLAW_SESSION_KEY=agent:main:main
```

Restart the dashboard with `docker compose up --build -d`. The token is read by the backend only; it is never sent to the browser. The OpenClaw Gateway must accept the dashboard backend as an authenticated local operator client.

## Voice commands

The voice worker listens locally for **Hey Jarvis** using openWakeWord. Only
the short command recorded after a wake detection is sent to OpenAI for
transcription.

1. Set `OPENAI_API_KEY` in `.env`. The USB microphone is configured as
   `plughw:2,0`; change `VOICE_AUDIO_DEVICE` if ALSA assigns it differently.
2. Start the worker alongside the dashboard:

   ```sh
   docker compose -f compose.yaml -f compose.pi.yaml --profile voice up -d --build
   ```

The worker stops recording shortly after you finish speaking (with a six-second
maximum), then forwards the transcript to the backend. It does not retain
recordings.

Supported commands include: “play Spotify Yuuri”, “change artist to YOASOBI”,
“stop the music”, “turn the volume up/down”, “set volume to 50 percent”, and
“turn the lights on/off”. Volume controls the Raspberry Pi OS HDMI mixer, not
Spotify volume. The dashboard lists the same command set.

If it triggers repeatedly, increase `VOICE_WAKEWORD_THRESHOLD` and restart the
voice container. The worker will not accept another wake detection until the
model score has been below that threshold for `VOICE_WAKEWORD_REARM_SECONDS`.

## Local development

1. Copy `.env.example` to `.env` and fill only values required for the active phase.
2. Run `docker compose up --build`.
3. Open `http://localhost:8080` on the Pi.

On the Raspberry Pi, include the hardware override:

```sh
docker compose -f compose.yaml -f compose.pi.yaml up --build -d
```

The production dashboard intentionally binds to `127.0.0.1`. Do not expose it to the LAN or internet until Phase 6 authentication is implemented.

## BroadLink RM4 Mini setup

The RM4 Mini is an **IR-only** remote. It can control the light only when the
light's existing remote emits infrared; it cannot control RF-only remotes.

1. Add the RM4 Mini to the BroadLink mobile app on the same 2.4 GHz network as
   the Pi, and reserve its DHCP address in the router.
2. Discover its exact device data from the Pi:

   ```sh
   docker compose -f compose.yaml -f compose.pi.yaml run --rm backend python -m app.tools.discover_broadlink
   ```

   Copy `host`, `mac`, and decimal `device_type` from the matching RM4 Mini
   line into `BROADLINK_HOST`, `BROADLINK_MAC`, and
   `BROADLINK_DEVICE_TYPE` in `.env`. RM4 Mini hardware revisions use
   different device type IDs, so do not guess this value.
3. Start the dashboard with the Pi override, then learn both light buttons:

   ```sh
   docker compose -f compose.yaml -f compose.pi.yaml up -d --build
   docker compose -f compose.yaml -f compose.pi.yaml run --rm backend python -m app.tools.learn_broadlink
   ```

   Point the original remote at the RM4 Mini and press ON when prompted, then
   OFF. The packets are saved in `data/learned-codes/lights.json`, which is
   intentionally ignored by Git.
4. Restart the backend with the same Compose files and use the light control
   on the dashboard. A failed command never changes the recorded light state.

## Project layout

- `backend/` — FastAPI, device integrations, scheduling, database.
- `frontend/` — React dashboard, kiosk keyboard controls.
- `voice/` — reserved for the independent wake-word/audio worker.
- `deploy/` — systemd units for Compose and Chromium kiosk startup.
- `docs/` — implementation plan and interface contracts.
- `data/` — persistent SQLite database and learned IR code files; never commit.

## Deployment principle

Docker owns application services. Chromium remains a host-level systemd service because HDMI kiosk display, screen blanking, Bluetooth audio, and desktop-session integration are more reliable outside a browser container.
