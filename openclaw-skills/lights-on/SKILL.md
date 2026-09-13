---
name: lights-on
description: One-tap command that turns the Chili room lights on.
user-invocable: true
disable-model-invocation: true
metadata: { "openclaw": { "requires": { "bins": ["bash", "curl"] } } }
---

# Lights on

Immediately run this command with the `exec` tool:

```bash
bash {baseDir}/../light-control/scripts/light-control.sh on
```

Do not ask which action the user wants and do not ask for confirmation. Report
success only when the JSON response has `"status": "success"`; otherwise report
the concise error.
