# Chili efficiency — handoff for another agent

Copy this whole file into another agent. It is enough to implement the efficiency cuts without the prior chat.

Read `docs/agent-handoff-chili.md` first for product, Toshi, and Daily OS rules. This file is only the **waste-cut**. It does not replace that document.

- **Human:** Takatoshi (“Toshi”)
- **Repo:** `github.com:Taching/home-dashboard.git`
- **Live host:** Raspberry Pi wall kiosk + Tailscale phone
- **Timezone:** Asia/Tokyo
- **Reviewed:** 13 Sep 2026, then tightened the same day after an implementation-risk review
- **Canonical cut order:** 1 → 4 → 3 → 2 → 5

---

## Mission of this pass

**Keep the glance and the Telegram loop. Remove leftover API and agent calls that do not change what Toshi sees.**

Target after all five cuts, one kiosk tab, quiet hour:

| Metric | Now | After |
| --- | --- | --- |
| Wall + integration calls / hour | ~2,466 | ~318 |
| OpenClaw gateway handshakes / hour | ~1,800 | 0 |
| Live Notion queries / hour | ~180 | ~12 (5-minute cache) |
| Workout-log OpenClaw work | 1 `chat.send` agent turn + 1 `notify_user` | 0 agent turns; 1 `notify_user` |

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

`GET /api/v1/plan/{day}` and `GET /api/v1/daily/{day}` are the same function (`DailyPlanService.build`). That object already has today/tomorrow training, meetings, priority tasks, walk/sober glance reminders, `last_adjustment`, `week_quality`, `bjj_candidates`, and `tomorrow.prescription`.

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
2. Calls `_ask_chili` → `openclaw.send()` (one agent turn + `DashboardContextProvider` snapshot)
3. Falls back to `local_workout_review()` which already writes 3–6 factual lines
4. Then `_notify_chili` → `notify_user` (Telegram, not an agent turn). Today the notify body is **advice only** — it does not put the daily URL on line one.

Sunday weigh-in already texts `saved.notify_message` (URL first). Then `_ask_chili(saved.review_prompt)` starts a second agent turn for page advice.

`notify_user` must stay. `chat.send` on these paths must go.

`DashboardContextProvider` is still too large for any remaining `chat.send` (real Telegram questions). A later nicety is to inject a short Daily Plan snippet instead of house internals. Not required for cuts 1–4.

### 4. Two skill doors and two training writes

| Stack | Module | What still uses it |
| --- | --- | --- |
| Planner | `app.domain.training.TrainingService` | Daily page, wall overview, evening coach, adjust-calendar |
| Legacy log | `app.domain.training_logs.TrainingService` | `/workout`, `/training/plans`, `/training/log`, OpenClaw NL parse |

`POST /daily/{day}/workout` and `POST /training/workout` both log, then both call `review_logged_workout`. `/workout` can write **both** stores.

`WorkoutApp` **reads** completion from legacy `TrainingToday.logs` (`GET /training/today`). `PlanPage` also auto-calls `logWorkout` to sync a legacy log into the planner (`frontend/src/pages/WorkoutApp.tsx`). Changing only the write path will show an unsaved workout after reload, or re-fire logs and notifies.

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

## The five cuts

**Canonical order: Cut 1 → Cut 4 → Cut 3 → Cut 2 → Cut 5.**

Cut 2’s Notion checks assume Cut 3’s cache exists. Stop after 1+4 if Toshi asked for the cheap win only. Separate commits are fine.

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

### Cut 4 — Local review + Telegram; no `chat.send`

**Do**

- `review_logged_workout`: use `local_workout_review` only. Do not call `_ask_chili`.
- Telegram must keep the daily URL on the first line. Store **advice only** on wellbeing (no URL in that field):

```python
wellbeing.store_advice(day, advice)
_notify_chili(request, f"{_daily_url(day)}\n\n{advice}", f"workout-review:{session_id}")
```

- Sunday: keep `_notify_chili(request, saved.notify_message, ...)`. That string is already URL-first (`WeeklyService.notify_message`). Do **not** call `_ask_chili(saved.review_prompt)`.
- Sunday page `advice`: keep the normal composed Daily Plan advice from `_briefing` (`compose_today_advice`). Do not invent a new weekly-review essay. Do not write `saved.notify_message` into wellbeing advice.
- Keep `_ask_chili` out of the file if unused. Do not wire it back “for personality.” Optional OpenAI voice rewrite on adjust-calendar can stay.

**Do not**

- Stop Telegram on workout / Sunday / evening.
- Put the daily URL anywhere but the first line of those notifies.
- Prefix the URL onto the stored wellbeing advice string.

**Check**

- Log a workout on `/daily/YYYY-MM-DD`: page returns immediately; Telegram starts with `/daily/YYYY-MM-DD`; backend logs show `notify_user`, not `chat.send`.
- Sunday weigh-in: one notify (`saved.notify_message`); page still shows composed Daily Plan advice; no agent turn.
- Evening job unchanged: Python coach, notify, OpenAI only if the week actually changed.

### Cut 3 — Cache Notion

**Do**

- Cache `NotionService.today()` in-process for ~5 minutes with a monotonic clock (`time.monotonic`).
- Hold one `httpx.Client` on the service. Close it from the FastAPI lifespan shutdown (same place `main.py` cancels jobs).
- Serialize cache refreshes (a lock) so concurrent `/plan/{day}` requests do not both query Notion.
- On Notion failure: keep the last successful snapshot if one exists (same pattern as `WeatherService`). Do not cache a failure as empty-ready. A short negative TTL (e.g. 30s) is OK if there is no last-good snapshot.
- Invalidate only after a **successful** `complete()`. Other Notion methods that create temporary clients (`publish_progress`, etc.) should use the shared client too if you touch them; do not leave `today()` on a singleton and `complete()` opening a throwaway client that cannot see invalidation.
- After invalidate, the next `today()` must hit Notion.

**Do not**

- Cache calendar bridge snapshots in this pass (already local SQLite).
- Cache Spotify now-playing.

**Check**

- Two `/plan/{day}` calls within 5 minutes do not hit Notion twice.
- After a successful `complete_task`, the next plan build sees the change.
- A failed Notion query still returns the previous task list if one was cached.

### Cut 2 — Wall polls Daily Plan + cheap dashboard

**Prerequisite (Cut 3).** Notion on the wall becomes the cached plan tasks.

Daily Plan today does **not** include `week`, `upcoming`, `countdowns`, `phase`, `trends`, or `readiness`. `TrainingWeekStrip` uses `training.upcoming ?? training.week` and `bjj_candidates`. `TrainingInsights` uses `phase`, `tomorrow` **as a training session**, `tomorrow_prescription`, `week_quality`, `last_adjustment`, `countdowns`. `Header` also uses `training.phase`, `training.readiness?.weight_kg`, and `training.trends.weight_7d_average`.

`DailyBriefing.tomorrow` is a **full day block**. `TrainingOverview.tomorrow` is a **session**. A spread or `training={plan}` will break the week strip, insights, and header weight.

**Do — payload**

From the **existing** `training.overview()` call inside `build()` (do not query overview twice), add enough fields that this adapter is total:

```ts
{
  generated_at: overview.generated_at,
  timezone: plan.timezone,
  phase: overview.phase,
  today: plan.today.training,
  tomorrow: plan.tomorrow.training,          // session, not the day block
  week_start: overview.week_start,
  week: overview.week,
  upcoming: overview.upcoming,
  countdowns: overview.countdowns,
  compliance: overview.compliance,
  week_quality: plan.tomorrow.week_quality ?? overview.week_quality,
  tomorrow_prescription: plan.tomorrow.prescription,
  last_adjustment: plan.last_adjustment,
  bjj_candidates: plan.tomorrow.bjj_candidates ?? overview.bjj_candidates,
  trends: overview.trends,                   // Header uses weight_7d_average
  readiness: overview.readiness,             // Header uses readiness.weight_kg
}
```

Prefer a named helper `trainingOverviewFromPlan(plan)` over pretending `DailyBriefing` is `TrainingOverview`. Longer-term, teach Header / week strip / insights a plan type. Do not do that rewrite in this pass unless the adapter is clearly more dangerous.

**Do — polling**

- `useDashboardData.refresh()`: `fetchDashboard` + `fetchSpotifyNowPlaying` + `fetchDailyPlan`. Drop `fetchTrainingOverview` from the 60s loop.
- Drop the 30s `fetchNotionToday` loop. Task rail reads `plan.today.tasks`.
- Keep `/calendar/events` at 15 minutes. The day grid is a 30-day window; Daily Plan only has today + tomorrow meetings.
- Keep `/walkingpad/today` at 30s for the live badge.
- Keep Spotify at 60s.

**Do — walk reminder (do not change its meaning)**

There are two walk objects. Do not collapse them into one string.

| Object | Job | Shape |
| --- | --- | --- |
| Glance reminder | Hero / daily “steps left” | `{ id, kind, title, detail }` from `_reminders()` |
| Nudge reminder | Wall banner via `useChiliNotifications` | `{ active, message, dedupe_key }` from `WalkingPadService.reminder(events)` |

`reminder()` is calendar-aware, hour-window-aware, meeting-gap-aware, and uses a stable `walk:window:{date}:{next_event}` dedupe key (`backend/app/domain/walkingpad.py`). The controller requires `active`, `message`, and `dedupe_key` (`chiliNotificationController.ts`).

If you stop polling `GET /walkingpad/reminder`:

1. Call `walking.today(now)` **once** in `build()`.
2. Pass that snapshot into both `_reminders()` and `reminder()` (add an optional snapshot argument if needed). Do not query walking twice.
3. Put the existing nudge object on the plan, e.g. `walk_reminder: { active, message, dedupe_key }`. Same semantics, same message, same dedupe key.
4. Point `useChiliNotifications` at `plan.walk_reminder`.

Do **not** replace the nudge with the glance “steps left” item.

**Do not**

- Persist a Daily Plan table.
- Hide the week strip or tournaments.
- Make Notion a 30s live feed again.

**Check**

- Week strip still shows the next six days, including BJJ candidates as `BJJ?`.
- Header still shows phase taper hint and 7-day average weight when present.
- How/Why from `last_adjustment` still appears on wall and `/daily`.
- Walk banner still respects meeting gaps and the existing dedupe key.
- Completing a Notion task via OpenClaw updates the wall on the next plan poll after cache invalidate.

### Cut 5 — One skill door; `/workout` reads and writes `TrainingSession`

This is the dedicated collapse plan that `docs/agent-handoff-chili.md` said not to do blindly.

**Do, in this order**

1. OpenClaw: one mutate door. Prefer `daily-os` `adjust-calendar` / `plan-control.sh` for NL and plan verbs. In `bjj-training/SKILL.md`, tell the agent to use daily-os for `adjust-calendar`, confirm/decline BJJ, fatigue, gym-today, rest. Keep bjj-training for **policy + read** (`today` / `week` / `plan` templates) and session status (`complete` / `skip` / `metrics`) if those PATCH routes stay.
2. Phone `/workout` **write:** `POST /api/v1/daily/{day}/workout` only. Stop calling `logWorkout` / `POST /training/workout` as a second source of truth.
3. Phone `/workout` **read:** completion, exercises, notes, and “already saved” must come from `TrainingSession` (daily plan `workout` / planner `for_date` / a planner field on `/training/today`). Do **not** decide saved-ness from `today.logs` (`TrainingLog`).
4. Remove the automatic legacy-to-planner sync effect in `PlanPage` (`WorkoutApp.tsx` — the `useEffect` that calls `logWorkout` when `existing` is set and `planner_status === 'planned'`). That effect will otherwise re-submit and can notify again.
5. Reload of `/workout/{slug}` must still show the workout as saved, with ticks and note, from `TrainingSession`.
6. Keep `training_logs` **templates** (`/training/plans`, written program text) until `WORKOUT_TEMPLATES` is the only program text. Do not delete the module in the first commit.
7. Leave `/training/log` NL parse briefly if OpenClaw still uses it; prefer daily-os + planner after that.

**Do not**

- Delete `training_logs.py` and hope `/workout` still renders.
- Invent a third log table.
- Collapse evening coach or `CalendarAdjuster` into the agent.
- Leave the sync `useEffect` in place “just in case.”

**Check**

- One Telegram “Strength A today” → one adjust call → one week rewrite → one How/Why notify.
- `/workout` log updates the same session the wall and `/daily` show.
- Reload after save still shows saved. A second load or submit does **not** create a duplicate `TrainingLog`, a second planner write, or a second Telegram notify.
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
- `frontend/src/components/Header.tsx` — `phase`, `readiness.weight_kg`, `trends.weight_7d_average`

**Read model**

- `backend/app/domain/daily_plan.py`
- `backend/app/api/daily.py`
- `frontend/src/lib/api.ts` (`fetchDailyPlan` vs `fetchDailyBriefing`)
- `frontend/src/types.ts` — `DailyBriefing` vs `TrainingOverview`

**Agent / notify**

- `backend/app/domain/openclaw.py` (`history` reconnects every call; `notify_user` is the Telegram path)
- `backend/app/domain/training/review.py` (`local_workout_review`)
- `backend/app/domain/training/adjust.py` (fast-path + optional OpenAI + How/Why)
- `backend/app/domain/training/coach.py` (evening; already local-first)
- `backend/app/domain/weekly.py` — Sunday `notify_message` is already URL-first
- `backend/app/domain/dashboard_context.py` (too large; later)

**Integrations**

- `backend/app/domain/notion.py`
- `backend/app/domain/walkingpad.py` — `reminder()` must keep its semantics
- `backend/app/domain/spotify.py` (keep 60s now-playing)

**Duplicate doors**

- `backend/app/api/training.py` — `/automation/training/adjust` and `/automation/training/run`
- `openclaw-skills/daily-os/`
- `openclaw-skills/bjj-training/`
- `frontend/src/pages/WorkoutApp.tsx` — read path + sync `useEffect`

---

## Suggested first slice if time is short

Cuts **1 and 4 only**. They are waste, not product. They do not need the Daily Plan week-array change.

Then 3, then 2, then 5.

---

## Test plan

Backend:

- Existing tests in `backend/tests/test_daily_plan.py`, `test_training_review.py`, `test_training_adjust.py`, `test_training_coach.py`, `test_openclaw.py` must stay green.
- Add or extend: workout log does not call `openclaw.send`; workout notify is `url + blank + advice`; Sunday does not call `openclaw.send`; Notion `today()` is cached and locked; plan payload includes week/upcoming/countdowns/phase/trends/readiness/`walk_reminder` after cut 2.

Wall (Pi or local frontend):

- Load `/`. No OpenClaw transcript. Advice + Spotify still there.
- Week strip, header weight/phase, and tomorrow How/Why still render.
- Leave the tab open 5 minutes. Network panel should not show `/openclaw/messages/stream`.
- `/daily/YYYY-MM-DD` log workout → Telegram starts with the daily URL, no long hang.
- Walk banner still stays quiet when a meeting is too soon.

OpenClaw:

- `adjust-calendar "rest today"` still replans and texts How/Why.
- `plan-control.sh today` still returns the plan object.

`/workout`:

- Save, reload, still saved. Second visit does not notify again.

---

## Non-goals

- Do not profile the Pi or add metrics dashboards.
- Do not pool OpenClaw WebSockets unless you are already in `openclaw.py` for another reason. Cut 1 removes the hot path.
- Do not merge `router.py` splits, voice, lights, or display work into this branch.
- Do not “improve Chili’s voice” with more model calls.

---

## Originating review

13 Sep 2026. Findings came from reading the wall poll hooks, `OpenClawService._request`, `DailyPlanService.build`, `review_logged_workout`, both OpenClaw skills, and the two `TrainingService` classes. Quiet-hour numbers are interval math for one kiosk tab, not measured tcpdump.

A follow-up review the same day caught missing `/workout` read-path instructions, walk-reminder semantics, the Daily Plan → `TrainingOverview` adapter, URL-first notify construction, Notion client lifecycle, the agent-turn label, and the contradictory cut order. Those are now in this file.
