# Implementation plan

## System boundary

The FastAPI backend is the sole authority for all device actions. The React UI, keyboard controls, and future voice worker send commands to it; none may call BroadLink or I2C directly.

```text
React kiosk / keyboard ─┐
                       ├─> FastAPI ─> SHT31, BroadLink, SQLite
Voice worker (Phase 2) ─┘
```

## Phase 1 — foundation and hardware dashboard

**Deliverable:** the monitor shows current conditions and persists data after reboot.

1. Configure FastAPI, SQLite migrations, health checks, WebSocket events, and a local-only reverse proxy.
2. Add the SHT31 adapter and poll it every 300 seconds.
3. Add BroadLink discovery and encrypted/local learned-code storage, then implement on/off commands.
4. Build the kiosk dashboard: current temperature, humidity, light state, last-updated time, integration health, and a 24-hour chart.
5. Add keyboard fallbacks: `L` light toggle, `S` screen toggle, `R` refresh.
6. Install systemd units: Compose starts after network availability; Chromium opens the dashboard in kiosk mode.

**Acceptance criteria**

- A Pi reboot restores the API, dashboard, database, and kiosk automatically.
- Sensor readings continue to persist during a 24-hour test.
- The dashboard clearly indicates a sensor or BroadLink failure without crashing.
- UI and keyboard commands produce an audited light event.

## Phase 2 — voice

**Deliverable:** English commands work while the dashboard screen is black.

1. Build push-to-talk recording and transcription first.
2. Add strict command parsing and command endpoint calls.
3. Verify Bose Bluetooth output reconnects after reboot.
4. Add Picovoice Porcupine with the custom Raspberry Pi `Hey Chili` model.
5. Add silence-based recording, OpenAI transcription, concise TTS responses, and a voice-state indicator.

Allowed V1 intents: `light.turn_on`, `light.turn_off`, `sensor.get_temperature`, `sensor.get_humidity`, `display.show`, `display.hide`, `system.get_status`.

Unknown transcription must fail closed: speak a short error and take no device action. Never retain microphone recordings after transcription.

## Phase 3 — scheduling and history

- Default dashboard visibility schedule: 10:00–19:00 Asia/Tokyo.
- Manual screen commands override the current scheduled state until the next schedule boundary.
- Add 7-day and 30-day sensor trends.
- Add optional explicit AI summaries of retained sensor data; never send data automatically.

## Phase 4 — personal integrations

- Google Calendar read-only upcoming-events panel.
- Notion task query and completion state.
- Integration credentials are server-side and not exposed to the React bundle.

## Phase 5 — phone control and additional appliances

- Responsive local dashboard with authenticated actions.
- TV, AC, brightness, and warmth commands after each device has repeatable BroadLink codes.

## Phase 6 — remote access

- Add authentication, authorization, audit review, and backups first.
- Use a private network tunnel such as Tailscale. Do not directly publish the Pi dashboard to the internet.

## API contract

```text
GET  /api/v1/health
GET  /api/v1/dashboard
GET  /api/v1/readings?from=<ISO>&to=<ISO>
POST /api/v1/commands
WS   /api/v1/events
```

`POST /api/v1/commands` accepts only allowlisted intents:

```json
{ "intent": "light.turn_on", "source": "ui" }
```

Each attempt creates a `device_events` record with its source, result, and safe diagnostic detail.

