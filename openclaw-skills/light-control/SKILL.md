---
name: light-control
description: Turn the Chili room lights on or off and report the last light command.
user-invocable: false
metadata: { "openclaw": { "requires": { "bins": ["bash", "curl"] } } }
---

# Light control

Use this skill when the user asks to turn the room lights or dashboard-controlled
lights on or off, or asks for their current status.

Run exactly one of these commands with the `exec` tool:

```bash
bash {baseDir}/scripts/light-control.sh on
bash {baseDir}/scripts/light-control.sh off
bash {baseDir}/scripts/light-control.sh status
```

Use `on` for requests to turn on the lights and `off` for requests to turn them
off. Use `status` for state questions. The BroadLink controller is one-way, so a
status response reports the last successful command rather than sensing the
physical light directly.

Treat these Telegram control-panel callbacks as direct action requests:

- `callback_data: lights_on` means run the `on` command.
- `callback_data: lights_off` means run the `off` command.

Do not ask for confirmation after either callback; execute it and report the
result.

Confirm an on/off action only when the JSON response has `"status": "success"`.
If it fails, say the light command failed and include the concise error. Do not
call BroadLink or send IR commands directly.
