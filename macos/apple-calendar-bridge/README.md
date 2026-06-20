# Apple Calendar bridge

This macOS helper reads the calendars already visible in Apple Calendar and uploads a rolling 30-day snapshot, including all-day and timed events, to the Chili Dashboard. It is read-only: it does not alter Calendar events.

## 1. Prepare the Pi

Generate a long random token on a trusted machine:

```sh
openssl rand -hex 32
```

Put it in the Pi project's `.env` as `APPLE_CALENDAR_BRIDGE_TOKEN=<token>`. Also add `CALENDAR_BRIDGE_BIND_ADDRESS=0.0.0.0`, then start the dashboard with the extra bridge service:

```sh
docker compose -f compose.yaml -f compose.pi.yaml -f compose.apple-calendar-bridge.yaml up --build -d
```

This adds port `8081` on the Pi's home-network address. It accepts only `POST /api/v1/calendar/apple/sync`; every other route returns 404. The main dashboard remains local-only on port `8080`. The bridge binds to `127.0.0.1` by default, so it is not accidentally exposed on development machines.

## 2. Build and authorize the Mac helper

From this directory on the Mac that has your calendars:

```sh
zsh build-app.sh
DASHBOARD_URL=http://raspberrypi.local:8081 \
CALENDAR_BRIDGE_TOKEN='<the same token>' \
"build/Chili Calendar Bridge.app/Contents/MacOS/chili-calendar-bridge"
```

Run this first command while logged into the Mac. macOS will ask for Calendar access; choose **Allow Full Access**. Verify the dashboard Calendar region then shows today’s events.

All-day events appear in a compact strip above the kiosk timeline.

## 3. Sync every five minutes

Copy `com.chili.calendar-bridge.plist` to `~/Library/LaunchAgents/`, replace all three `REPLACE_WITH_...` values (use the full path to `build/Chili Calendar Bridge.app` for `REPLACE_WITH_APP_PATH`), then load it:

```sh
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.chili.calendar-bridge.plist 2>/dev/null || true
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.chili.calendar-bridge.plist
```

The bridge must run in the logged-in desktop session because macOS grants Calendar permission to that user session. The job deliberately launches the app through macOS rather than executing its binary directly; this preserves the Calendar permission context. If the Mac is asleep or offline, the dashboard keeps the most recent events and shows the Calendar region as unavailable after 15 minutes.

## Troubleshooting

- Confirm both personal and work accounts appear in the Mac Calendar app.
- Use the Pi’s actual hostname or LAN IP if `raspberrypi.local` does not resolve.
- Check `/tmp/chili-calendar-bridge.error.log` for launchd failures.
- Treat the bridge token as a password. Do not put it in a committed plist or send it in chat.
