# Chili efficiency — handoff for another agent

Copy this whole file into another agent. It is enough to implement the efficiency cuts without the prior chat.

Read `docs/agent-handoff-chili.md` first for product, Toshi, and Daily OS rules. This file is only the **waste-cut**. It does not replace that document.

- **Human:** Takatoshi (“Toshi”)
- **Repo:** `github.com:Taching/home-dashboard.git`
- **Live host:** Raspberry Pi wall kiosk + Tailscale phone
- **Timezone:** Asia/Tokyo
- **Reviewed:** 13 Sep 2026 against the uncommitted Daily OS / training tree
- **Canvases (optional):** efficiency review and before/after live beside the originating chat; this file is the source of truth for implementation

---

## Mission of this pass

**Keep the glance and the Telegram loop. Remove leftover API and agent calls that do not change what Toshi sees.**

Target after all five cuts, one kiosk tab, quiet hour:

| Metric | Now | After |
| --- | --- | --- |
| Wall + integration calls / hour | ~2,466 | ~318 |
| OpenClaw gateway handshakes / hour | ~1,800 | 0 |
| Live Notion queries / hour | ~180 | ~12 (5-minute cache) |
| Agent turns when he logs a workout | 2 (`chat.send` + notify) | 0 agent; 1 `notify_user` |

He should still see Today, the week strip, meetings, tasks, Spotify, Chili’s advice, and Telegram How/Why. He should **not** see the OpenClaw transcript column.

Do **not** restyle the kiosk. Do **not** add features.

---

## What is wrong (findings)

### 1. The wall streams OpenClaw every 2 seconds

`frontend/src/main.tsx` still mounts `OpenClawChat`.
`useDashboardData` opens `EventSource('/api/v1/openclaw/messages/stream')`.

That SSE loop calls `OpenClawService.history()` every 2s. Each call opens a **new** gateway WebSocket, completes the challenge, authenticates, then asks `chat.history`. If telegram-session preference is on, `sessions.list` can also run every 30s.

The product handoff already marks the transcript column as outdated. Telegram is the conversation surface.

`useChiliNotifications` can still read OpenClaw messages for on-wall banners. After this pass, **do not** keep a 2s stream for banners. Either drop those banners (preferred: Telegram already has the text) or poll `/openclaw/messages` at 60s. Do not leave the SSE on.

### 2. Daily Plan is already the glance model, then the wall polls it again

`GET /api/v1/plan/{day}` and `GET /api/v1/daily/{day}` are the same function (`DailyPlanService.build`). That object already has today/tomorrow training, meetings, priority tasks, walk/sober reminders, `last_adjustment`, `week_quality`, `bjj_candidates`, and `tomorrow.prescription`.

The kiosk still polls in parallel:

| Interval | Calls |
| --- | --- |
| 60s | `/dashboard` + `/spotify/now-playing` + `/training/overview` + `/plan/{day}` |
| 30s | `/notion/today` (live Notion, no cache) + `/walkingpad/today` + `/walkingpad/reminder` |
| 15 min | `/calendar/events` (30-day window) |
| 30 min | `/weather` (server cache 20 min — fine) |

`plan.build()` itself calls `training.for_date` twice, `training.overview()`, and `notion.today()`. So Notion and overview run again inside the 60s plan poll.

`NotionService.today()` POSTs the Notion data source on every call and constructs a new `httpx.Client` each time.

### 3. Workout and Sunday start an agent to rewrite local text

`review_logged_workout` in `backend/app/api/daily.py`:

1. Builds a prompt with `workout_review_prompt`
2. Calls `_ask_chili` → `openclaw.send()` (full agent turn + `DashboardContextProvider` snapshot: sensors, lights, 14-day calendar, training, Notion, Spotify)
3. Falls back to `local_workout_review()` which already writes 3–6 factual lines
4. Then `_notify_chili` → `notify_user` (second WebSocket, Telegram)

Sunday weigh-in does the same: notify, then `_ask_chili` for advice.

`notify_user` must stay. `chat.send` on these paths must go.

`DashboardContextProvider` is still too large for any remaining `chat.send` (real Telegram questions). A later nicety is to inject a short Daily Plan snippet instead of house internals. Not required for cuts 1–4.

### 4. Two skill doors and two training writes

| Stack | Module | What still uses it |
| --- | --- | --- |
| Planner | `app.domain.training.TrainingService` | Daily page, wall overview, evening coach, adjust-calendar |
| Legacy log | `app.domain.training_logs.TrainingService` | `/workout`, `/training/plans`, `/training/log`, OpenClaw NL parse |

`POST /daily/{day}/workout` and `POST /training/workout` both log, then both call `review_logged_workout`. `/workout` can write **both** stores.

OpenClaw skills:

- `openclaw-skills/daily-os/` — plan verbs + `adjust-calendar` via `POST /automation/plan`
- `openclaw-skills/bjj-training/` — same mutate verbs + `adjust-calendar` via `POST /automation/training/adjust`

Same `CalendarAdjuster`. An agent can fetch overview, then plan, then pick a script.

`GET /daily/{day}` ≡ `GET /plan/{day}`. Frontend has both `fetchDailyBriefing` and `fetchDailyPlan`.

### 5. Quality drag (do not boil the ocean)

- `backend/app/api/router.py` is ~1,737 lines (dashboard, Spotify, voice, OpenClaw, walking pad, leftover training routes). Daily and planner already split out. Do not rewrite the router in this pass.
- Two classes named `TrainingService`.
- `POST /daily/{day}/check-in` still accepts sleep / soreness / 1–5 readiness. Do not revive those fields.
- `TrainingService.overview()` loads **every** `TrainingMetric` row. Fix only if you touch overview; not a first cut.

---

## The five cuts (implement in this order)

Do them as separate commits if Toshi wants commits. Otherwise one branch is fine. Stop after cut 1+4 if he asked for the cheap win only.

### Cut 1 — Stop the OpenClaw stream on the wall

**Do**

- Unmount `OpenClawChat` from `frontend/src/main.tsx`. Keep `ChiliAdvice` and `MediaRegion`.
- Remove the EventSource / 5s fallback in `useDashboardData`.
- Stop fetching OpenClaw history on boot unless you keep a 60s banner poll (see above). Prefer dropping wall OpenClaw state entirely.
- Leave `OpenClawService.history()` and `/openclaw/messages` in the backend. Phone and tools may still want them later.

**Do not**

- Remove `notify_user`, `/chili/notify`, or Telegram delivery.
- Put the transcript back as a primary column.

**Check**

- Kiosk left rail: advice + Spotify. No “Chili Agent” transcript.
- Quiet hour: no 2s `/openclaw/messages/stream` in nginx/backend logs.
- Telegram still receives morning URL, evening How/Why, and notify tests.

### Cut 2 — Wall polls Daily Plan + cheap dashboard

**Prerequisite:** Daily Plan must carry what the week strip and insights need. Today it does **not** include the full `week` / `upcoming` / `countdowns` arrays. `TrainingWeekStrip` uses `training.upcoming ?? training.week` and `bjj_candidates`. `TrainingInsights` also uses `phase`, `tomorrow`, `tomorrow_prescription`, `week_quality`, `last_adjustment`, `countdowns`.

**Do**

- Add those fields to `DailyPlanService.build()` from the existing `training.overview()` call (it already runs inside `build`). Do not add a second overview query.
- Point the wall week strip / insights / last-adjustment banner at `plan` (or a thin adapter from plan → the current `TrainingOverview` shape).
- `useDashboardData.refresh()`: `fetchDashboard` + `fetchSpotifyNowPlaying` + `fetchDailyPlan`. Drop `fetchTrainingOverview` from the 60s loop.
- Drop the 30s `fetchNotionToday` loop. Tasks on the wall come from `plan.today.tasks` (or plan-level tasks you already serialize).
- Keep `/calendar/events` at 15 minutes. The day grid is a 30-day window; Daily Plan only has today + tomorrow meetings.
- Keep `/walkingpad/today` at 30s while a session can be live. Fold `/walkingpad/reminder` into Daily Plan reminders; do not poll both.
- Keep Spotify at 60s. It is now-playing, not glance data.

**Do not**

- Persist a Daily Plan table.
- Hide the week strip or tournaments.
- Make Notion a 30s live feed again.

**Check**

- Week strip still shows the next six days, including BJJ candidates as `BJJ?`.
- How/Why from `last_adjustment` still appears on wall and `/daily`.
- Completing a Notion task via OpenClaw still updates the wall within the cache TTL (cut 3), not instantly.

### Cut 3 — Cache Notion

**Do**

- Cache `NotionService.today()` for ~5 minutes (in-process TTL is enough on the Pi).
- Reuse one `httpx.Client` instead of open/close per call.
- Invalidate on `complete()` so a Telegram “mark that task done” can refresh on the next plan poll.

**Do not**

- Cache calendar bridge snapshots in this pass (already local SQLite).
- Cache Spotify now-playing.

**Check**

- Two `/plan/{day}` calls within 5 minutes do not hit Notion twice.
- After `complete_task`, the next plan build sees the change.

### Cut 4 — Local review + Telegram; no `chat.send`

**Do**

- `review_logged_workout`: use `local_workout_review` only, then `_notify_chili`. Delete the `_ask_chili` call on this path.
- Sunday handler: keep `_notify_chili(saved.notify_message, ...)`. Do not call `_ask_chili(saved.review_prompt)`.
- Store the local advice on wellbeing if the daily page still shows `advice`.
- Keep `_ask_chili` out of the file if unused, or leave it unused — do not wire it back “for personality.” `explain_adjustment` + `SOUL.md` on adjust-calendar is enough. Optional OpenAI voice rewrite on adjust can stay for now; do not add a new one.

**Do not**

- Stop Telegram on workout / Sunday / evening.
- Put the daily URL anywhere but the first line of those notifies.

**Check**

- Log a workout on `/daily/YYYY-MM-DD`: page returns immediately; Telegram gets the local note; backend logs show `notify_user` / `send` channel, not `chat.send`.
- Sunday weigh-in: one notify, no agent turn.
- Evening job unchanged: Python coach, notify, OpenAI only if the week actually changed.

### Cut 5 — One skill door; `/workout` writes `TrainingSession`

This is the dedicated collapse plan that `docs/agent-handoff-chili.md` said not to do blindly.

**Do, in this order**

1. OpenClaw: one mutate door. Prefer `daily-os` `adjust-calendar` / `plan-control.sh` for NL and plan verbs. In `bjj-training/SKILL.md`, tell the agent to use daily-os for `adjust-calendar`, confirm/decline BJJ, fatigue, gym-today, rest. Keep bjj-training for **policy + read** (`today` / `week` / `plan` templates) and session status (`complete` / `skip` / `metrics`) if those PATCH routes stay.
2. Phone `/workout` log buttons should `POST /api/v1/daily/{day}/workout` (or a thin wrapper that only writes `TrainingSession`). Stop writing `TrainingLog` as a second source of truth.
3. Keep `training_logs` **templates** (`/training/plans`, written program text) until `WORKOUT_TEMPLATES` is the only program text. Do not delete the module in the first commit.
4. Leave `/training/log` NL parse for a short while if OpenClaw still uses it; prefer daily-os + planner after that.

**Do not**

- Delete `training_logs.py` and hope `/workout` still renders.
- Invent a third log table.
- Collapse evening coach or `CalendarAdjuster` into the agent.

**Check**

- One Telegram “Strength A today” → one adjust call → one week rewrite → one How/Why notify.
- `/workout` log updates the same session the wall and `/daily` show.
- `GET /api/v1/calendar/apple/training-plan` still comes from `TrainingService.calendar_plan()`.

---

## What must not change

- Competition policy in `backend/app/domain/training/policy.py` and `openclaw-skills/bjj-training/SKILL.md`
- Fatigue is four states via OpenClaw. No morning questionnaire.
- Wall stays read-only. Phone and Telegram write.
- Daily notify: **URL on the first line.** Never “tick this.”
- `notify_user` ≠ `chat.send`. Never use `chat.send` to deliver a Telegram ping.
- Tailscale only. No Funnel.
- No Daily Plan persistence table.
- No Mac voice-first shell, no hybrid-ai-fitness set logging.
- Do not commit `.env` or `backend/chili_dashboard_backend.egg-info/`.
- Restart the kiosk after a frontend image rebuild or Chromium keeps the old bundle.

---

## Key files

**Wall polling**

- `frontend/src/hooks/useDashboardData.ts`
- `frontend/src/hooks/useStartupBoot.ts`
- `frontend/src/main.tsx`
- `frontend/src/components/OpenClawChat.tsx`
- `frontend/src/hooks/useChiliNotifications.ts`

**Read model**

- `backend/app/domain/daily_plan.py`
- `backend/app/api/daily.py`
- `frontend/src/lib/api.ts` (`fetchDailyPlan` vs `fetchDailyBriefing`)

**Agent / notify**

- `backend/app/domain/openclaw.py` (`history` reconnects every call; `notify_user` is the Telegram path)
- `backend/app/domain/training/review.py` (`local_workout_review`)
- `backend/app/domain/training/adjust.py` (fast-path + optional OpenAI + How/Why)
- `backend/app/domain/training/coach.py` (evening; already local-first)
- `backend/app/domain/dashboard_context.py` (too large; later)

**Integrations**

- `backend/app/domain/notion.py`
- `backend/app/domain/spotify.py` (keep 60s now-playing)

**Duplicate doors**

- `backend/app/api/training.py` — `/automation/training/adjust` and `/automation/training/run`
- `openclaw-skills/daily-os/`
- `openclaw-skills/bjj-training/`
- `frontend/src/pages/WorkoutApp.tsx`

---

## Suggested first slice if time is short

Cuts **1 and 4 only**. They are waste, not product. They do not need the Daily Plan week-array change.

Then cut 3 (small). Then cut 2 (needs the plan payload). Then cut 5 (behavior + skills; easiest to get wrong).

---

## Test plan

Backend:

- Existing tests in `backend/tests/test_daily_plan.py`, `test_training_review.py`, `test_training_adjust.py`, `test_training_coach.py`, `test_openclaw.py` must stay green.
- Add or extend: workout log does not call `openclaw.send`; Sunday does not call `openclaw.send`; Notion `today()` is cached; plan payload includes week/upcoming/countdowns after cut 2.

Wall (Pi or local frontend):

- Load `/`. No OpenClaw transcript. Advice + Spotify still there.
- Week strip and tomorrow How/Why still render.
- Leave the tab open 5 minutes. Network panel should not show `/openclaw/messages/stream`.
- `/daily/YYYY-MM-DD` log workout → Telegram, no long hang.

OpenClaw:

- `adjust-calendar "rest today"` still replans and texts How/Why.
- `plan-control.sh today` still returns the plan object.

---

## Non-goals

- Do not profile the Pi or add metrics dashboards.
- Do not pool OpenClaw WebSockets unless you are already in `openclaw.py` for another reason. Cut 1 removes the hot path.
- Do not merge `router.py` splits, voice, lights, or display work into this branch.
- Do not “improve Chili’s voice” with more model calls.

---

## Originating review

13 Sep 2026. Findings came from reading the wall poll hooks, `OpenClawService._request`, `DailyPlanService.build`, `review_logged_workout`, both OpenClaw skills, and the two `TrainingService` classes. Quiet-hour numbers are interval math for one kiosk tab, not measured tcpdump.
