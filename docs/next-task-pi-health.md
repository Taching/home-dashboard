# Next task: Raspberry Pi health panel

## Goal

Add read-only Raspberry Pi health information to the dashboard: CPU usage, memory usage, CPU temperature, load average, and uptime. This is separate from the SHT31 room temperature and humidity readings.

## Data source

Use a small host-metrics collector that reads the Pi’s Linux system files:

- CPU use: `/proc/stat`
- Memory: `/proc/meminfo`
- CPU temperature: `/sys/class/thermal/thermal_zone0/temp`
- Load average: `/proc/loadavg`
- Uptime: `/proc/uptime`

Do not scrape `btop`. `btop` is useful for manual SSH diagnosis, but it is an interactive terminal UI rather than a stable API. The dashboard collector should report the same underlying host metrics in JSON.

## Architecture

```text
Pi host /proc + /sys
        ↓ read-only mounts
pi-health collector container
        ↓ private Docker network
FastAPI system-health endpoint
        ↓
React Pi Health panel
```

- Keep host filesystem access out of the main dashboard backend.
- Give the collector read-only `/proc` and `/sys` mounts only; no Docker socket, shell endpoint, or LAN-exposed port.
- FastAPI normalizes the collector response at `GET /api/v1/system/health`.
- Health polling belongs to the shared dashboard data layer, not a new component-level timer. Its refresh interval, stale threshold, and cache TTL must come from backend-owned configuration.

## Refactor prerequisite

Complete the data-fetching foundation before adding the panel. The current dashboard has overlapping polling effects and duplicated timing values in React and Python; adding Pi health to that pattern would add unnecessary requests and make stale-state behavior inconsistent.

- Move operational values (poll intervals, stale windows, request timeouts, cache TTLs, ranges, and limits) into backend settings. Return non-sensitive UI values with the dashboard configuration or snapshot response.
- Replace independent polling effects with resource hooks backed by one scheduler. Fetch only integrations that are configured, abort superseded requests, and pause scheduled work when the page is hidden or offline.
- Remove effects that derive state from existing props/state. Use render-time calculations, event handlers, reducers, or memoization where appropriate.
- Retain effects only for external synchronization with a clear cleanup path: clock timer, browser event listeners, Spotify SDK lifecycle, and deliberate polling/subscriptions. The objective is not to eliminate every `useEffect`; it is to remove effects that create redundant state, duplicate requests, or re-attach work unnecessarily.
- Add resource-level loading, error, and last-success states so a failed refresh does not silently look current.

## API response

```json
{
  "status": "ready",
  "sampled_at": "2026-06-21T10:00:00Z",
  "cpu_percent": 18.4,
  "cpu_temperature_c": 54.2,
  "memory_used_bytes": 2318401536,
  "memory_total_bytes": 8589934592,
  "load_1m": 0.42,
  "uptime_seconds": 123456
}
```

## UI

- Add a compact `PI HEALTH` region in the left environment column.
- First row: CPU %, memory %, and Pi CPU temperature.
- Supporting row: one-minute load and uptime.
- Normal is cyan, warning is amber, critical is red.
- Suggested thresholds:
  - CPU temperature: warning 75°C; critical 80°C.
  - CPU: warning 85%; critical 95%.
  - Memory: warning 85%; critical 95%.
- Show `Live`, `Stale` after five minutes, or `Unavailable` if the collector fails.

## Validation

- Compare displayed values with `btop` while connected to the Pi by SSH.
- Confirm memory total and CPU use represent the Pi host, not the dashboard container.
- Compare CPU temperature with `vcgencmd measure_temp`.
- Confirm the collector has no write access to host files and no LAN-exposed port.
- Test normal, warning, critical, stale, unavailable, 1920×1080, and narrow-screen states.

## Other planned work

1. **Activate OpenClaw chat:** add the Pi gateway URL and token to `.env`, then confirm shared Telegram delivery and transcript synchronization.
2. **Install the Apple Calendar launch agent:** run the five-minute Mac bridge so the dashboard no longer marks Calendar stale after 15 minutes.
3. **Notion integration:** read-only overdue/today task panel once credentials are provided.
4. **Voice service:** wake word, transcription, and routing to the existing dashboard/OpenClaw command paths.
5. **Comfort automation:** optional display schedule, brightness/warmth, and later TV/AC BroadLink controls.
6. **Secure remote access:** authentication and Tailscale before any access outside the home network.
