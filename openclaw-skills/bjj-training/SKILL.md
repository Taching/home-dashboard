---
name: bjj-training
description: View and control the Chili BJJ competition training plan, readiness, workout completion, metrics, rescheduling, replacement, and added BJJ sessions.
user-invocable: false
metadata: { "openclaw": { "requires": { "bins": ["bash", "curl"] } } }
---

# BJJ competition training

Use this skill for questions or actions about today's/tomorrow's training, the
weekly plan, readiness, BJJ, strength, Zone 2, grip, workout completion, or
competition preparation. The dashboard API is the authority; never invent a
different workout or silently add missed work.

Run one matching command with the `exec` tool:

```bash
bash {baseDir}/scripts/training-control.sh today
bash {baseDir}/scripts/training-control.sh tomorrow
bash {baseDir}/scripts/training-control.sh week
bash {baseDir}/scripts/training-control.sh plan strength_a
bash {baseDir}/scripts/training-control.sh plan strength_b
bash {baseDir}/scripts/training-control.sh start SESSION_ID
bash {baseDir}/scripts/training-control.sh complete SESSION_ID [NOTES]
bash {baseDir}/scripts/training-control.sh partial SESSION_ID [NOTES]
bash {baseDir}/scripts/training-control.sh skip SESSION_ID [REASON]
bash {baseDir}/scripts/training-control.sh move SESSION_ID ISO_DATETIME_WITH_OFFSET
bash {baseDir}/scripts/training-control.sh replace SESSION_ID WORKOUT_TYPE
bash {baseDir}/scripts/training-control.sh recovery SESSION_ID
bash {baseDir}/scripts/training-control.sh add-bjj ISO_DATETIME_WITH_OFFSET [normal|hard]
bash {baseDir}/scripts/training-control.sh metrics SESSION_ID METRICS_JSON
```

Valid replacements are `strength_a`, `strength_b`, `zone_2`, `bjj_technical`,
`bjj_normal`, `bjj_hard`, `recovery`, and `rest`. For bike intervals, send one
metric per round, for example:

```json
[{"metric_type":"bike_rpm","sequence":1,"value":95,"unit":"rpm"},{"metric_type":"bike_rpm","sequence":2,"value":94,"unit":"rpm"}]
```

Treat these Telegram callbacks as direct requests and use the session ID after
the colon: `training_complete:`, `training_partial:`, `training_skip:`, and
`training_recovery:`. Do not ask for confirmation. After an action, report the
updated plan and its reason from the API. A skipped session must stay skipped
unless the deterministic scheduler finds a safe future slot.

Daily readiness, training completion, and sobriety check-ins are submitted on
the private daily briefing page. When asked to collect or chase a check-in,
send the dated `/daily/YYYY-MM-DD` page link instead of asking questions in chat.

After `completed` or `partial`, request only the metrics relevant to that session:

- BJJ: rounds completed, typical rest seconds, session RPE, and final-round quality 1–5.
- Strength A: session RPE plus each bike round's watts, RPM, distance, or calories—prefer the first metric the bike exposes consistently.
- Strength B: session RPE and any modified or missed exercise.
- Zone 2: duration, average/max heart rate, distance, and pace when available.

Submit numeric values through `metrics`; do not ask for unrelated fields or turn
the check-in into a long questionnaire.

When the user asks what a named gym workout contains—even when it is not
scheduled today—run `plan strength_a` or `plan strength_b`. Present every
exercise in order with load, sets, reps, duration, notes, conditioning, and the
estimated session time. Do not schedule or record the workout merely because
the user asked to view it.
