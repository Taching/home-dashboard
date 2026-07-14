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

2. On the Mac that contains the calendars, build and authorize the bundled helper, then install its LaunchAgent for fifteen-minute syncs. macOS must grant **Calendar Full Access** and the Mac must remain logged in. Follow the exact commands in [macos/apple-calendar-bridge/README.md](macos/apple-calendar-bridge/README.md).

## OpenClaw shared chat

The Ask Chili panel uses the existing OpenClaw main session and mirrors replies to Telegram. On the Pi, add the following to `.env`, using the gateway’s local token:

```env
OPENCLAW_GATEWAY_WS_URL=ws://host.docker.internal:18789
OPENCLAW_GATEWAY_TOKEN=<gateway token>
OPENCLAW_SESSION_KEY=agent:main:main
```

Restart the dashboard with `docker compose up --build -d`. The token is read by the backend only; it is never sent to the browser. The OpenClaw Gateway must accept the dashboard backend as an authenticated local operator client.

## WalkingPad S1

The dashboard can track daily walking from a KingSmith WalkingPad S1 over BLE and show progress in the header. OpenClaw receives the same stats in its private context snapshot, and Chili can nudge you to walk when there is at least one hour free before your next meeting between 10:00 and 20:00.

1. Find the pad BLE name on the Pi:

   ```sh
   bluetoothctl scan on
   ```

2. Add to `.env`:

   ```env
   WALKINGPAD_BLE_NAME=KS-HD-XXXX
   WALKINGPAD_BRIDGE_TOKEN=<long random token>
   WALKINGPAD_GOAL_MINUTES=120
   WALKINGPAD_GOAL_DISTANCE_KM=3.0
   WALKINGPAD_REMINDER_START_HOUR=10
   WALKINGPAD_REMINDER_END_HOUR=20
   WALKINGPAD_MIN_GAP_BEFORE_MEETING_MIN=60
   WALKINGPAD_MIN_SESSION_MINUTES=15
   ```

3. Start the BLE collector alongside the dashboard:

   ```sh
   docker compose -f compose.yaml -f compose.pi.yaml --profile walkingpad up -d --build
   ```

Close the KS Fit app on your phone while the collector runs; the treadmill allows only one BLE client at a time. The collector uses host networking and D-Bus on the Pi so it can reach the pad reliably.

### Manual walk logs

When BLE tracking misses a session, log it manually:

- **Ask Chili chat** on the dashboard: `I walked 30 min and 2 km today`
- **OpenClaw / Telegram**: ask Chili to log the walk; it can call the automation API using `DASHBOARD_AUTOMATION_TOKEN`
- **Script**:

  ```sh
  deploy/openclaw-log-walk.sh 30 2
  deploy/openclaw-log-walk.sh "walked 30 min and 2 km today"
  ```

  ```sh
  curl -fsS -X POST http://127.0.0.1:8080/api/v1/automation/walkingpad/log \
    -H "Authorization: Bearer $DASHBOARD_AUTOMATION_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"duration_minutes":30,"distance_km":2}'
  ```

Manual sessions are added to today's totals in the header and OpenClaw context.

### Historical DB read for OpenClaw

OpenClaw (or any automation client) can read date-scoped dashboard SQLite data
with the same bearer token. Spotify OAuth secrets are excluded.

```sh
# One day
curl -fsS -H "Authorization: Bearer $DASHBOARD_AUTOMATION_TOKEN" \
  http://127.0.0.1:8080/api/v1/db/2026-07-13

# Last 7 days starting from a date
curl -fsS -H "Authorization: Bearer $DASHBOARD_AUTOMATION_TOKEN" \
  'http://127.0.0.1:8080/api/v1/db/2026-07-07?days=7'

# July (inclusive range)
curl -fsS -H "Authorization: Bearer $DASHBOARD_AUTOMATION_TOKEN" \
  'http://127.0.0.1:8080/api/v1/db/2026-07-01?end=2026-07-31'

# Helper
./deploy/openclaw-db-read.sh 2026-07-13
./deploy/openclaw-db-read.sh 2026-07-07 days=7
```

The response includes a `summary` (walk minutes/km/steps, sensor averages, counts)
plus full row lists for sensors, walks, lights, pump runs, voice logs, calendar
events, and notify dedupe keys for that local-date range.

## Notion tasks

The task rail reads incomplete Notion tasks due today or overdue. Create a
Notion internal integration, share the task database or data source with that
integration, then add the connection values to `.env`:

```env
NOTION_TOKEN=<internal integration secret>
NOTION_DATA_SOURCE_ID=<preferred current Notion data source id>
# or, for older database URLs:
NOTION_DATABASE_ID=<database id>
NOTION_TITLE_PROPERTY=Name
NOTION_DUE_PROPERTY=Due Date
NOTION_DONE_PROPERTY=Done
NOTION_STATUS_PROPERTY=Status
NOTION_DONE_STATUSES=Done,Complete,Completed
```

The default property names expect a title named `Name`, a date named
`Due Date`, and either a checkbox named `Done` or a status named `Status`.
Adjust the names if your database uses different labels, then rebuild/restart
the backend.

## Voice commands

The voice worker listens locally for **Hey Chili** using the bundled
`assets/voice/hey_chee_lee.tflite` openWakeWord model. Only
the short command recorded after a wake detection is sent to OpenAI for
transcription.

1. Set `OPENAI_API_KEY` in `.env`. The USB microphone is configured as
   `plughw:2,0`; change `VOICE_AUDIO_DEVICE` if ALSA assigns it differently.
   By default, Compose mounts `./assets/voice/hey_chee_lee.tflite` into the voice
   container at `/models/hey_chee_lee.tflite`.
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

**Hey Chili not responsive?** The bundled model is custom-trained; official
models like Hey Jarvis are tuned on much more data. Retrain with the
[openWakeWord Colab notebook](https://colab.research.google.com/drive/1q1oe2zOyZp7UsB3jJiQ1IFn8z5YfjwEb?usp=sharing)
and install via `./deploy/install-wakeword-model.sh`. See
[docs/voice-wakeword-training.md](docs/voice-wakeword-training.md) for the full
workflow and a mic benchmark tool to compare models.

## Local development

1. Copy `.env.example` to `.env` and fill only values required for the active phase.
2. Start the dashboard from the project root:

   ```sh
   ./start.sh
   ```

   The launcher starts the dashboard, voice worker, and Apple Calendar bridge.
   It detects a Raspberry Pi and includes its hardware configuration
   automatically. It runs the containers in the background and builds updated
   images when necessary.
3. Open `http://localhost:8080` on the Pi.

For a development machine without one of those integrations, exclude it:

```sh
./start.sh --no-voice --no-calendar
```

Use `./start.sh --foreground` to keep logs in the terminal, and
`./start.sh --help` to see all options. Stop the stack with `docker compose down`
(include `-f compose.pi.yaml` when stopping it on a Pi).

On the Raspberry Pi, include the hardware override:

```sh
docker compose -f compose.yaml -f compose.pi.yaml up --build -d
```

The dashboard binds to `127.0.0.1:8080` by default. For a cleaner
dashboard-only view, add `?mode=kiosk` to the dashboard URL. On refresh, a
startup splash checks backend, calendar bridge, Notion, Spotify, OpenClaw, and
weather before revealing the dashboard. Hover the bottom center of the screen to switch
**Full** vs **Lite** motion (saved in the browser; toggling reloads the page).
Lite mode keeps voice and Spotify equalizer animations but drops the heaviest
GPU effects. Chromium CPU flags in `deploy/chili-kiosk.service` also help. For
phone access away from the Pi, use the Tailscale Serve setup below instead of
exposing the dashboard directly to the LAN or internet.

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

## SwitchBot plant pump

The dashboard can water plants through a SwitchBot Plug via the Cloud Open API.
Manual control lives in the left column as **Plant pump**; OpenClaw can trigger
the same 20-second pulse each morning.

1. In the SwitchBot app, open **Profile → About** and tap the version number
   ten times to reveal **Developer Options**. Copy the **token** and **secret**
   into `.env` as `SWITCHBOT_TOKEN` and `SWITCHBOT_SECRET`.
2. Discover the plug device ID:

   ```sh
   docker compose -f compose.yaml -f compose.pi.yaml run --rm backend python -m app.tools.discover_switchbot
   ```

   Copy the plug ID into `SWITCHBOT_PLUG_DEVICE_ID`.
3. Generate a long random `DASHBOARD_AUTOMATION_TOKEN` in `.env`.
4. Rebuild and restart the dashboard stack.
5. Schedule OpenClaw (or host cron) to call the automation endpoint at
   **08:00 Asia/Tokyo**:

   ```sh
   # ~/.config/chili/plant-water.env
   DASHBOARD_AUTOMATION_TOKEN=your-token-here
   CHILI_DASHBOARD_URL=http://127.0.0.1:8080
   ```

   ```cron
   0 8 * * * /home/takatoshi/Work/home-dashboard/deploy/openclaw-plant-water.sh
   ```

   OpenClaw on the same Pi should use `http://127.0.0.1:8080`. If the cron job
   runs elsewhere, point `CHILI_DASHBOARD_URL` at your Tailscale dashboard URL
   instead.

   If watering fails, the dashboard asks OpenClaw to notify you on Telegram.

## Project layout

- `backend/` — FastAPI, device integrations, scheduling, database.
- `frontend/` — React dashboard, kiosk keyboard controls.
- `voice/` — reserved for the independent wake-word/audio worker.
- `deploy/` — systemd units for Compose and Chromium kiosk startup.
- `docs/` — implementation plan and interface contracts.
- `data/` — persistent SQLite database and learned IR code files; never commit.

## Deployment principle

Docker owns application services. Chromium remains a host-level systemd service because HDMI kiosk display, screen blanking, Bluetooth audio, and desktop-session integration are more reliable outside a browser container.

## Remote phone access

Use Tailscale Serve to access the dashboard privately from a phone while away
from home. It does not require router port forwarding and keeps the dashboard
off the public internet. See [docs/tailscale-remote-access.md](docs/tailscale-remote-access.md).
