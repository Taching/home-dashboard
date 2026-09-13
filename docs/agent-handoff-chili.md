# Chili dashboard — handoff for another agent

Copy this whole file into another agent. It is enough to analyze the product without the prior chat.

- **Human:** Takatoshi (“Toshi”)
- **Repo:** `github.com:Taching/home-dashboard.git`
- **Live host:** Raspberry Pi, wall HDMI (ASUS VG278), Chromium kiosk
- **Timezone:** Asia/Tokyo
- **Phone access:** Tailscale only (`https://chili-dashboard.tail95606b.ts.net`). No Funnel. Prefer Safari.
- **Do not treat this as a generic fitness app.** It is a one-person personal daily OS.

---

## Who Toshi is (product context)

Toshi lives in Tokyo (Minato). He trains **BJJ first**, with strength and cardio around it. Two competitions matter:

- 9th All Japan Jiu-Jitsu Championship — 10–11 Oct 2026 (taper from 5 Oct)
- ASJJF Asian Open — 7–8 Nov 2026 (taper from 2 Nov)

He is cutting toward **74 kg**. He tracks a **sober streak** (baseline 22 Aug 2026 + 7 days). He walks on a WalkingPad. The house has lights (BroadLink), a plant pump (SwitchBot), Apple Calendar, Notion tasks, Spotify, and OpenClaw/Chili on Telegram.

Workdays are often meeting-heavy. Chili must look like a work day when the calendar is packed, and like a training day on a competition Saturday.

He does **not** want:

- Hybrid-ai-fitness set-by-set logging
- A restyled “voice-first” kiosk (that Mac shell is the outdated wall UI)
- A second walk / calendar / activity tracker
- A morning readiness form (sleep, fatigue, soreness, pain, motivation)
- Public internet exposure of the dashboard
- The wall becoming a second Notion or an equal four-widget dashboard

Sleep from Garmin is a later idea only (`docs/garmin-fenix-integration.md`).

---

## Mission

**Chili should tell Toshi what matters today across work, meetings, tasks, training, and home life, then help him prepare for tomorrow.**

The loop:

**Work + Meetings + Tasks + Training + Home reminders → Daily Plan → Reminder → Action → Confirmation → Replan**

Home reminders are walk, vitamins, dinner, and sober — not lights, pump, Bluetooth, or display internals.

### Interfaces

| Surface | Job |
| --- | --- |
| **Wall** `/` | Read-only glance. One Today hero from the Daily Plan; meetings, tasks, and training as supporting density. |
| **Phone** `/daily/YYYY-MM-DD` | Close the loop for today’s plan items: workout ticks, evening sober, Sunday weigh-in. Not a second Notion. |
| **`/workout`** | Written program text for the gym. Reference only. |
| **OpenClaw** | Conversational verbs over the same canonical data. Then Chili replans forward. |

Chili should text the **daily URL first**, never “tick this.” Tailscale only.

### Daily Plan

One read model, not a fourth write store. Sources stay canonical:

- Meetings = Apple Calendar (non-training)
- Tasks = Notion today
- Training = `TrainingSession`
- Home reminders = walk / sober / existing reminder jobs

`GET /api/v1/daily/{day}` and `GET /api/v1/plan/{day}` return the same object. Wall and phone both consume it. `today` + `tomorrow` include headline, emphasis, training, meetings, tasks, reminders, and a prepare-tomorrow line.

### Training source of truth

The competition policy in `backend/app/domain/training/policy.py` and `openclaw-skills/bjj-training/SKILL.md` is authoritative. Calendar, confirmed BJJ, completed/skipped sessions, fatigue state, and work load are the changing facts.

Planned and completed training live on `TrainingSession`. Header weekly BJJ/strength counts are **status**, not a success score. `week_quality` is Excellent / Good / Acceptable / Bad planning. Notion progress reports **derive from session status**. `DailyWellbeingCheckIn` keeps **sober, weight, and fatigue_state** (`normal` / `tired` / `very_fatigued` / `pain`). Leftover 1–5 readiness fields are unused by the planner. Do not invent a parallel gym/BJJ count from check-in booleans.

BJJ candidates are proposed days, not timed sessions, until Toshi confirms them or they appear on Apple Calendar. A skipped lift is decided for that week unless he explicitly moves it. Recompute the remaining week after a change; do not slide the missed session to tomorrow.

Two training stacks still live together on purpose — do not collapse them in this pass:

| Name | Module | Job |
| --- | --- | --- |
| `training_service` | `app.domain.training` | Planner, sessions, wall overview, daily workout ticks |
| `training_log_service` | `app.domain.training_logs` | Gym/BJJ/sober NL log, `/training/plans`, `/training/log`, `/workout` text |

### Planner vs work load

Timed Apple events are busy blocks (slots 06:00–14:00). That prevents an 18:30 gym after a 9–18 calendar. **Load also changes the prescription:** a packed workday, late finish, travel, or dinner should drop or shorten extra gym even if a morning slot is free. BJJ calendar events stay pinned.

### Overrides

OpenClaw should prefer `adjust-calendar` for natural-language plan changes. That path uses AI (with a local fast-path for common phrases), writes `TrainingSession`, replans the remaining week, then syncs Notion and the Apple/Chili Training calendar. It also sends a How/Why notification in Chili’s `SOUL.md` / `IDENTITY.md` voice and stores `last_adjustment` for the wall and daily page. Skills must not override that personality. Explicit verbs (`rest-today`, `gym-today`, `move-gym`) still work. The wall stays read-only.

`GET /api/v1/calendar/apple/training-plan` now serves `TrainingService.calendar_plan()`, not the legacy week-template events.

The 20:00 evening job (`POST /automation/training/run` action `evening`) reconciles Apple Calendar first, then a coach pass can place missing Strength B / Zone 2 on a true Open day, move gym off a packed workday, or protect rest. It always notifies How / Why / tomorrow. Empty days stay empty unless a tournament target is still missing.

---

## How a normal week should feel

| Day | Wall | Phone |
| --- | --- | --- |
| Sunday | Rest (often); Daily Plan still shows meetings/tasks | Weigh-in vs last week + week review; evening sober |
| Work-heavy weekday | Today hero is meetings + tasks; training is compact | After work/class: tick what happened |
| BJJ / competition Saturday | Today hero is training; calendar is supporting | After class: tick rounds/work + note |
| Strength / Zone 2 / grip / rest | Whatever the planner kept after work-load | Log if there was work; evening sober |

Walks stay on the existing WalkingPad tracker. Do not add a second one.
Empty calendar time is **not** an invitation to add fatigue.

---

## Architecture (enough to analyze)

```
Wall Chromium kiosk  →  http://127.0.0.1:8080?performance=1
Phone Safari         →  https://chili-dashboard.tail95606b.ts.net/daily/...

frontend (nginx :8080)
   → backend FastAPI
   → SQLite
   → Apple Calendar bridge (:8081)
   → Notion / Spotify / OpenClaw / BroadLink / SwitchBot / WalkingPad BLE
```

Live compose (Pi): `compose.yaml` + `compose.pi.yaml` + `compose.apple-calendar-bridge.yaml`  
Kiosk: `chili-kiosk.service` (system), user `takatoshi`, labwc, `WAYLAND_DISPLAY=wayland-0`  
Display power: `deploy/display-power.sh` + `wlr-randr` (HDMI-A-2)

### Key files

**Wall UI**

- `frontend/src/main.tsx` — kiosk shell vs `/daily` vs `/workout`
- `frontend/src/components/Header.tsx` — sober / weekly training / weight / walk / weather / clock
- `frontend/src/components/TodayHero.tsx` — Daily Plan glance
- `frontend/src/components/TrainingPlanner.tsx` — week strip, tomorrow, tournaments
- `frontend/src/components/PlanningRegion.tsx` — meetings calendar + tasks
- `frontend/src/styles.css` — Pi wall + daily page

**Phone**

- `frontend/src/components/DailyBriefingPage.tsx` — action page for the day’s plan
- `frontend/src/pages/WorkoutApp.tsx` — program pages

**Backend**

- `backend/app/domain/daily_plan.py` — Daily Plan read model + override verbs
- `backend/app/api/daily.py` — `GET /daily/{day}`, `GET /plan/{day}`, `POST .../workout|sober|sunday`, `POST /automation/plan`
- `backend/app/domain/training/` — scheduler (busy + work load), sessions
- `backend/app/domain/wellbeing.py` — sober / weight; weekly training counts from sessions
- `backend/app/jobs/sunday_review.py` — Sunday Telegram; URL must be first line

**Ops / OpenClaw**

- `openclaw-skills/bjj-training/` — training verbs + competition policy
- `openclaw-skills/daily-os/` — rest / move gym / fatigue / confirm-bjj / decline-bjj / move meeting / complete task
- `deploy/health-watchdog.sh`

### Important contracts

- Daily notify copy: **URL on the first line.** Never say “tick.”
- Preview query must not mutate the saved plan.
- Dashboard JSON includes `wellbeing` for the wall header. Gym/BJJ numbers come from `TrainingSession`.
- Kiosk must be restarted after a frontend image rebuild or Chromium keeps the old bundle.
- `POST /api/v1/automation/display` is what `display-control.sh` calls. If it 404s, Telegram cannot wake the monitor.
- OpenClaw `notify_user` has used a `target` field; gateway may require `to`.

---

## What “updated” vs “outdated” means

- **Updated (keep):** Daily OS wall — Today hero, meetings/tasks/training density, phone daily page, passive Spotify.
- **Outdated (do not put back on the wall):** Mac voice-first shell; OpenClaw transcript as a primary column; interactive light/pump/screen/volume; activity log as the left column.

`stash@{0}` (`WIP on master: ab2a356`) was the live Pi tree. Do **not** `git stash apply` blindly.

### Related handoff

Wall polling, OpenClaw SSE, duplicate Notion/training fetches, workout `chat.send`, and the two training stacks: copy `docs/agent-handoff-efficiency.md`. Product rules in **this** file still win.

---

## Non-goals for a follow-up agent

- Do not restyle the kiosk back to the Mac voice shell.
- Do not port hybrid-ai-fitness set logging.
- Do not add morning readiness fields. Fatigue is four states via OpenClaw.
- Do not enable Tailscale Funnel.
- Do not persist a Daily Plan table that copies calendar and Notion.
- Do not collapse `training_log_service` except as **Cut 5** in `docs/agent-handoff-efficiency.md`.
- Do not commit `.env` or `backend/chili_dashboard_backend.egg-info/`.
- Do not discard `stash@{0}` without asking; it is a backup of the live Pi work.
