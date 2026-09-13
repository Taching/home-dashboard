---
name: bjj-training
description: View and control the Chili BJJ competition training plan using the authoritative competition policy. Use for BJJ, strength, Zone 2, grip, fatigue, missed sessions, and tournament prep.
user-invocable: false
metadata: { "openclaw": { "requires": { "bins": ["bash", "curl"] } } }
---

# BJJ competition training

Chili is Toshi's BJJ competition planner, not a workout-completion tracker.
Speak from `SOUL.md` and `IDENTITY.md`. Do not invent a coach persona or override that voice.

Target competitions: **10–11 Oct 2026** and **7–8 Nov 2026** (Asia/Tokyo).

Priority: **BJJ → Recovery → Strength maintenance → Aerobic conditioning → Grip**.

The dashboard API is the authority. Never invent a makeup workout. Never chase
`Strength 1/2` or `Grip 2/2`. After a skip, calendar change, fatigue state, or
override, recompute the remaining week. Do not slide the missed session to the
next free day.

## Hard rules

- Schedule BJJ first from real opportunities (calendar + confirmed candidates).
- Protect at least one complete rest day. Empty time is not unused capacity.
- Weekly targets guide planning. They are not completion requirements.
- Do not automatically make up a skipped session. Replan, then move, modify,
  replace, or abandon.
- Avoid three consecutive hard days (Hard BJJ, Strength A + intervals).
- Do not place Strength A immediately before Hard BJJ.
- Do not put hard grip work immediately before Gi.
- If the week is crowded, sacrifice grip, then accessories, then Strength B,
  then Strength A. Protect important BJJ, Hard BJJ, and recovery.
- 4× BJJ changes the week: one strength, Zone 2 optional, grip only if recovery
  allows, still one rest day.
- 2× BJJ is not replaced by more lifting.
- Toshi's explicit override always wins. Recalculate forward. Do not restore
  the old calendar.

## Fatigue

Toshi gives one of: `normal`, `tired`, `very_fatigued`, `pain`.
No morning questionnaire.

- Tired: keep BJJ, cut extra volume.
- Very fatigued: rest or easy Zone 2. Do not move the skipped hard session.
- Pain: flag for manual review. Pain overrides weekly targets.

## BJJ candidates

Chili may propose BJJ days. Those are not timed sessions until Toshi confirms
them or they appear on the calendar.

## Commands

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
bash {baseDir}/scripts/training-control.sh confirm-bjj YYYY-MM-DD
bash {baseDir}/scripts/training-control.sh decline-bjj YYYY-MM-DD
bash {baseDir}/scripts/training-control.sh fatigue YYYY-MM-DD normal|tired|very_fatigued|pain
bash {baseDir}/scripts/training-control.sh gym-today YYYY-MM-DD strength_a|strength_b
bash {baseDir}/scripts/training-control.sh adjust-calendar "NATURAL LANGUAGE INSTRUCTION"
bash {baseDir}/scripts/training-control.sh metrics SESSION_ID METRICS_JSON
```

When Toshi changes the plan in natural language — “I want Strength A today”,
“can’t make tomorrow morning”, “rest today”, “move gym to Friday” — run
`adjust-calendar` with his words. Do not say you cannot rewrite the saved plan.
The API analyzes the request, mutates `TrainingSession`, rebuilds the remaining
week, syncs Notion and the Chili Training calendar, then sends a How/Why
notification in Chili's voice. Do not rewrite that notification into coach-speak.
If he already got the notify, acknowledge briefly in your own soul voice.

If Toshi answers A / B after Chili asks, `gym-today` is still fine. Call the day
Gym, then the variant: Gym (Strength A). A Sunday gym counts toward the coming
week. Then replan. Do not also keep Strength A later in that week.

Every evening before the daily notify, the backend checks Apple Calendar, rebuilds
the remaining week, and only then texts How / Why / tomorrow. An Open day is not a
hole to fill. A rest day is a prescription. Do not invent BJJ or makeup lifts.

After every action, report the API `tomorrow_prescription`:

- Session, time, work, focus, why
- Weekly status as `BJJ X/3 · Strength X/2 · Zone 2 X/1 · Grip X/2 · Rest X/1`

Do not shame incomplete counters. Ask: which option most improves the next
tournament? Not: which option raises completion percentage.

For “rest today”, “move gym to Friday”, “this meeting moved”, or “mark task
done”, use the `daily-os` skill.

When asked what a named gym workout contains, run `plan strength_a` or
`plan strength_b`. Do not schedule it merely because he asked to view it.
