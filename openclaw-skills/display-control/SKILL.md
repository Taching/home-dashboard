---
name: display-control
description: Turn the Chili dashboard monitor on or off and report its current power state.
user-invocable: false
metadata: { "openclaw": { "requires": { "bins": ["bash", "curl"] } } }
---

# Display control

Use this skill when the user asks to turn the dashboard monitor, screen, or display on or off, or asks whether it is currently on.

Run exactly one of these commands with the `exec` tool:

```bash
bash {baseDir}/scripts/display-control.sh on
bash {baseDir}/scripts/display-control.sh off
bash {baseDir}/scripts/display-control.sh status
```

Use `on` for requests to wake, show, or turn on the monitor. Use `off` for requests to sleep, hide, or turn off the monitor. Use `status` for state questions.

Treat these Telegram control-panel callbacks as direct action requests:

- `callback_data: monitor_on` means run the `on` command.
- `callback_data: monitor_off` means run the `off` command.

Do not ask for confirmation after either callback; execute it and report the
result.

Confirm the action only when the JSON response has `"status": "success"`. If the command fails, say the monitor command failed and include the concise error. Do not call `wlr-randr` or the low-level display script directly. Do not alter the automatic 08:00–22:00 schedule unless the user separately asks for a schedule change.
