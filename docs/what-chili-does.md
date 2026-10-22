# Chili — what this dashboard is and what it does

_Last updated: 22 Oct 2026 (floating chrome, Body switch, weekly data view, inline workout)_

## What it is for

Chili is my personal **daily OS**. It isn't a fitness app or a smart-home demo.
It looks at work, meetings, tasks, training, and home life together, tells me
**what matters today**, and helps me get ready for **tomorrow**.

The loop:

> Work + meetings + tasks + training + home reminders → **Daily Plan** → reminder → action → confirmation → replan

Right now everything points at one goal: the **21st All Japan Master Jiu-Jitsu
Championship, 5–7 Mar 2027 (Takasaki)**. That means BJJ first, strength and
cardio around it, and a steady weight cut toward lightweight.

It runs on a Raspberry Pi 5 with a wall monitor in kiosk mode. I reach it from my
phone over **Tailscale only** (`https://chili-dashboard.tail95606b.ts.net`). It
is never on the public internet.

---

## Where I use it

| Surface | What it's for |
| --- | --- |
| **Wall** (`/`) | Read-only glance. A Today hero, Chili's advice, the day's schedule, tasks and training. |
| **Phone: daily page** (`/daily/YYYY-MM-DD`) | Closing the loop for today: tick the workout, log sleep/weight, answer sober, Monday check-in. |
| **Phone: workout** (`/workout`) | Today's session inline: program first, then a compact log (load, reps, RPE; technique/pain under More). No advice block and no scheduler reason text. `/workout/{id}` opens another day's session. |
| **Phone: schedule change** (`/schedule-change`) | Tell Chili in plain words what changed; it replans the week. |
| **Phone: weekly** (`/weekly`) | Data first: adherence figure with the bottleneck chip, target meters, a Mon–Sun session strip (status icons + RPE, tap to open), recovery tiles, signed next-week deltas, then Confirm rebuild and Ask coach. All prose sits under one closed Details. |
| **Phone: exercises** (`/training/exercises`) | Exercise library, filters, and alternatives. |
| **Phone: weight / sober** (`/weight`, `/sober`) | History and trend pages with a Weight / Sober switch at the top; no page title or kicker. |
| **Phone: training preferences** (`/training/preferences`) | Free-text notes that give the coach context. They never change the schedule. |
| **Phone chrome** | Three floating pills at the top of every phone page, no bar: **Back** (history, else Today), Chili, burger menu. They slide away on scroll down and return on scroll up or near the top. Bottom **Today · Train · Week · Body** on hubs (hidden on another day's session and schedule-change). Burger groups Today hubs, Body (Weight/Sober), and Train tools (Change plan / Preferences / Exercises). |

Phone polish: exercise search uses shared styles and deep links (`/training/exercises/:slug`); schedule-change shows a week skeleton and “Open today / Open train” after a successful replan; sober’s only button is labeled **Log a drink (resets streak)**.
| **Telegram (Chili via OpenClaw)** | Morning/evening messages, reminders, and plain-language commands. |

---

## The wall

- **Header:** sober streak, BJJ and strength done vs. target this week, 7-day
  average weight vs. the cut target, **last night's sleep + HRV** (Garmin),
  steps vs. the 8,000 goal (WalkingPad or watch, whichever is higher),
  weather, and the clock.
- **Today hero + Chili's advice:** one lead line for the morning, lunch or
  evening window, plus a few points (walk, the next meeting, one task,
  tomorrow).
- **Schedule:** Apple Calendar meetings and training on an hourly grid,
  colour-coded by source: **work** (Asuene calendars) in cyan, **personal** in
  blue, **training** in green. If the Mac stops syncing, the **cached events
  stay up** with "Last updated HH:MM".
- **Tasks:** priority Notion tasks.
- **Training planner:** this week's sessions and status.
- **Banners:** a 10-minute heads-up before meetings, a walk nudge, plan
  changes, tasks completed, and Spotify. Banners only; meetings no longer go
  to Telegram.
- **Media:** Spotify now playing / DJ.
- **Screen schedule:** the monitor turns on at 08:00 and off at 22:00.

## The daily page (phone)

- Today's workout with tick-off, or a BJJ log (rounds, intensity). No
  scheduler reason text under the title.
- **Fenix card:** sleep, resting HR, HRV, Body Battery, steps, and the day's
  activities. On a rough night it adds one gentle recovery hint.
- Optional **sleep** and **morning weight** fields. They are never required.
- **Sober** answer for the evening.
- **Nutrition targets** for the day (training vs. rest day).
- **Monday check-in:** energy, hunger, BJJ performance, waist, pain, notes.
- **Close the day:** once the required answers are in, Chili writes a short
  local summary.
- **Ask coach:** an on-demand review of a logged workout. It's the only
  per-session AI call, and only when I press the button.

---

## Training

The planner (`TrainingSession`) is the single source of truth for what I
train. It writes to the Daily Plan, Notion, and a "Chili Training" Apple
calendar.

**Weekly targets (March plan):** 3 BJJ, 2 strength, 1–2 easy cardio, at least
1 full rest day. In the final six weeks (from 22 Jan): 4 BJJ and shorter
strength. Taper from 21 Feb. BJJ calendar classes are pinned, and gym work is
placed around them, my meetings, and workload.

### Strength A — Heavy Strength (50–60 min, RPE 7–8)

| Exercise | Sets × reps | Start |
| --- | --- | --- |
| Trap-bar deadlift | 3 × 3–4 | 125–130 kg |
| Dumbbell bench press | 3 × 6–8 | 30 kg/hand |
| Bulgarian split squat | 3 × 6–8/leg | 14 kg/hand |
| Cable row | 3 × 8–10 | RPE 7–8 |
| Pallof press | 3 × 10/side | moderate |
| Cable face pull | 3 × 12–15 | RPE 7 |

Plus a 5-minute bike warm-up and an **optional** 20–30 min easy cardio
finisher, which counts toward the cut's weekly cardio.

### Strength B — Athletic Strength (45–55 min, RPE 7–8)

| Exercise | Sets × reps | Start |
| --- | --- | --- |
| Kettlebell swing | 3 × 8 | moderate |
| Front squat | 3 × 4–5 | up to 90 kg |
| Military press | 3 × 5 | up to 52 kg |
| Weighted pull-up | 3 × 5–6 | BW + 5 kg |
| Romanian deadlift | 2 × 6 | up to 100 kg |
| Hanging knee raise | 3 × 8–12 | bodyweight (or lying leg raise) |

### Progressive overload

Reps first, then weight. **Weight only goes up after I log an RPE of 8 or
less.** A plain "done" tick holds the same weight.

| Exercise | Step |
| --- | --- |
| Deadlift / front squat / RDL | +5 kg at RPE ≤7, +2.5 kg at RPE 7.5–8 |
| Military press / weighted pull-up | +2.5 / +1 kg |
| Dumbbell bench / split squat | +2 kg/hand |
| Cable and core work | Top of the rep range, then one stack step |
| Kettlebell swing | Next bell (+4 kg) |

RPE 8.5 or shaky technique repeats the session. Pain, form breaking down, or
RPE 9 drops one set and about 7% of the weight. The first weight I log replaces
the starting target.

### Deload — every fourth week

Weeks of **9 Nov, 7 Dec, 4 Jan, 1 Feb**. About half the sets at 12.5% less
weight, never to failure, and BJJ that week gets a "technique first" note.
Fatigue signals (hard sessions, poor sleep, soreness) can bring a deload
forward. The taper replaces deloads from 21 Feb.

### Changing the plan

- Free text on `/schedule-change` or in Telegram ("skip tomorrow's BJJ",
  "gym today", "move gym to Friday", "this meeting moved"). Chili replans the
  rest of the week and sends a one-line summary plus the daily link.
- Fatigue is one of four states (normal / tired / very fatigued / pain). There
  is no morning questionnaire.

### Workout logging

On `/workout/:id` the **program is shown open above the log** so I see the prescription before filling fields. Each exercise has **one compact result** (not set-by-set):
- Load in kg, or a note like "BW + 5 kg" or "stack 8"
- Reps per set as a compact list: `8 / 8 / 7`
- Overall exercise RPE (drives next-session load)
- Technique and pain sit under **More** (optional mid-set)
- Status: completed, partial, or skipped

If lift or BJJ detail sync fails after the session status saves, the phone shows a clear error so I can retry — it no longer fails silently.

If I swap an exercise using the alternatives engine, both the **planned** and
**performed** exercise are recorded together with the substitution reason.
A plain "done" tick holds the weight — I must log an RPE to advance the load.

### BJJ session review

After BJJ I log:
- **Rounds** and **intensity** (required, as before)
- **Main focus** — e.g., "half guard sweeps" (optional)
- **Problem position** — e.g., "bottom half guard" (optional)
- **Primary failure tag** — from a fixed list of 12 (optional)
- **Success/attempt count** — only if the focus was measurable

This should take under 60 seconds. No technique statistics are required on
every session. The weekly analyzer surfaces recurring failures.

### Weekly analyzer (`/weekly`)

After the Monday check-in (or when I open `/weekly`), Chili recomputes a
**deterministic** Mon–Sun report with no AI call:

- Adherence (ordinary vs controllable when rain blocked a leave-home session)
- Strength trends (e1RM only within the same exercise slug; plain “done” holds load)
- Recurring BJJ failures / problem positions across distinct sessions
- Recovery context from sleep, fatigue state, pain flags, and Garmin wording
- A main bottleneck with a cause code (`execution`, `recovery`,
  `weather_constraint`, `technical_recurrence`, `possible_program_issue`, …)
  and expandable evidence keys

**Ask coach about this week** is a separate button. It explains the saved
facts only, never invents metrics, and never submits a schedule change.
**Use in schedule change** prefills `/schedule-change` so I still confirm.

### Rain handling

BJJ at the academy **requires travel**. When rain is at risk (precipitation
probability ≥50% or rain currently reported), the pre-workout message shows
a warning with three actions:

- **Move session** — reschedule to another day this week
- **Use home fallback** — solo drills or home cardio instead
- **Keep original plan** — go anyway

No response keeps the plan unchanged. **Weather never silently cancels a
session.** A rain-blocked miss counts as `weather_blocked`, not an execution
failure, and is excluded from "controllable adherence."

---

## Weight cut

- **Target:** lightweight (76.0 kg in the gi, ~74 kg in the morning).
  Middleweight is the fallback, decided **15 Jan 2027**.
- **Checkpoints** (7-day average, morning): 84 → 83 (2 Nov) → 80.5–81 (7 Dec)
  → 78.5–79 (4 Jan) → 76.5–77 (1 Feb) → 75–75.5 (22 Feb) → 74–74.5 (1 Mar).
- Progress is judged on the **7-day average**, never one day's number.
- **Food targets:** 2,300 kcal on training days, 2,000 on rest days, protein
  165–175 g, fat 60–70 g, carbs around training. Food itself is tracked in
  another app.
- At the Monday check-in, intake moves by ±150 kcal/day if the loss is faster
  than 0.75 kg/week, slower than 0.25 kg/week, or BJJ performance and energy
  are down. Nothing changes during the first 14-day trial.

---

## Garmin Fenix 8 Pro

Syncs every 30 min: sleep, sleep score, HRV, resting HR, Body Battery, stress,
steps, and activities. It's context only. **The watch never changes the plan.**

- Sleep fills the daily sleep field only if I left it empty.
- Watch steps count toward the walk goal.
- Weekly averages show in the Monday check-in.

---

## Telegram — what Chili sends me

| When | What |
| --- | --- |
| 06:00 | Daily link, a **Watch:** line, and a recovery hint after a rough night |
| ~60 min before a workout | Pre-workout reminder |
| ~30 min after a workout | Prompt to log it |
| 20:00 | Evening coach: tomorrow's session and any plan change |
| 21:00 / later | Sober question, then one follow-up if unanswered |
| Monday 10:00 | Weekly check-in |
| After a plan change | One-line summary + the daily link |
| 08:00 | Plant watering via the SwitchBot pump (automation) |

The AI budget is deliberately small: the coach only when I ask, plus the
Telegram replanning I trigger. Everything else (day close, weekly review,
advice, hints) is deterministic and runs on the Pi.

---

## Home

- **WalkingPad S1:** walks via Bluetooth, plus walk nudges between 10:00 and
  20:00 that avoid the hour before a meeting.
- **Lights** (BroadLink IR), **plant pump** (SwitchBot), **monitor on/off**,
  all through OpenClaw skills.
- **Room sensor:** temperature and humidity (SHT31).
- **Spotify:** now playing, DJ, and device transfer on the wall.
- **Health check:** a watchdog plus integration status for the calendar
  bridge, Notion, Spotify, OpenClaw, the WalkingPad, and Garmin.

---

## What it deliberately doesn't do

- No set-by-set logging app and no second walk/calendar/activity tracker.
- No morning readiness form (sleep, fatigue, soreness, motivation).
- The wall stays a read-only glance. It isn't a second Notion or a
  four-widget dashboard.
- No public internet. Remote access is Tailscale only.
- Training preferences and watch data inform the wording, never the scheduler.

---

## Where things live

| Thing | Source |
| --- | --- |
| Meetings | Apple Calendar → Mac bridge (`macos/apple-calendar-bridge/`) |
| Tasks | Notion, one or more task databases merged into one list |
| Training | `TrainingSession` (planner), mirrored to Notion and the "Chili Training" calendar |
| Sleep / weight / sober | `DailyWellbeingCheckIn`, plus Garmin snapshots |
| Code | `backend/` (FastAPI), `frontend/` (React kiosk + phone pages), `deploy/`, `openclaw-skills/` |
| Product rules | `docs/agent-handoff-chili.md` |
