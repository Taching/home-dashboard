# Noticeable Nudges Plan

> Future work — for reconsideration before implementation.

## Problem (today)

Walk/meeting alerts use a **small header pill** that:

- Auto-dismisses after **8 seconds**
- Has a **1.5px TTL bar** (easy to miss)
- Replaces the voice chip next to the logo — peripheral, not center of attention
- Leaves **no trace** after dismiss (session dedupe = gone for the session)
- **Walk reminders** do not send Telegram; **meetings** do

TTS runs via browser speech, but easy to miss if you're not facing the screen.

## Design principles

1. **Tier urgency** — meeting/walk ≠ Spotify/voice toasts
2. **Two moments** — interrupt (hard to miss) + record (verify later in Log)
3. **One dedupe per real event** — no conflicting double messages
4. **Respect reduced motion** — optional animation, TTS configurable
5. **Configurable** — TTL and channels in `.env`
6. **Use the Log panel** — you already watch it for Pi activity

## Recommended approach (3 layers)

### Layer A — Important nudges only (`meeting_soon`, `walk_reminder`)

| Change | Why |
|--------|-----|
| **Per-kind TTL** — 45–60s (not 8s) | Time to look up from desk/kitchen |
| **Persistent strip** after pill fades — e.g. `Walk nudge · 2:14pm` under header for 1h | Proof it fired if you missed the pill |
| **Log panel entry** — `notice · walk · "15 of 60 min…"` | Audit trail in panel you already use |
| **Telegram for walk** — same as meetings | Phone backup when not at the wall |
| **Stronger visual** — slightly larger pill, one pulse on entry | Glanceable from distance |

**Not** applied to `spotify_playing`, `voice_complete`, `task_completed` (keep 8s / subtle).

### Layer B — Acknowledgment (pick one)

- **Option 1 (light, recommended first):** persistent strip only — no click
- **Option 2 (medium):** pill stays until tap to dismiss (meeting + walk only)
- **Option 3 (heavy):** strip + explicit dismiss button

### Layer C — Activity log (durable)

Notifications are frontend-only today; Log reads `/api/v1/activity/events`.

When an important nudge fires, also log via existing `POST /api/v1/chili/notify` (or activity feed) so the **same event** shows in Log and Telegram once.

## Config (`.env.example`)

```env
CHILI_NOTICE_IMPORTANT_TTL_SECONDS=60
CHILI_NOTICE_IMPORTANT_STRIP_MINUTES=60
CHILI_NOTICE_WALK_TELEGRAM=true
CHILI_NOTICE_MEETING_TELEGRAM=true
CHILI_NOTICE_CASUAL_TTL_SECONDS=8
```

## Files to touch

- `frontend/src/lib/chiliNotifications.ts` — per-kind TTL
- `frontend/src/lib/chiliNotificationController.ts` — tiers, walk Telegram, log hook
- `frontend/src/components/ChiliNotificationBanner.tsx` — stronger visual
- New `NoticeStrip.tsx` + `Header.tsx` — persistent strip
- `frontend/src/styles.css`
- Tests: `chiliNotifications.test.ts`

## Out of scope (this plan)

- Voice log panel — **keep** (you use it for Pi debugging)
- System health CPU temp/load — **keep prominent**
- Garmin — see `docs/garmin-fenix-integration.md`
- Walking pad BLE reliability — separate
- Right rail / Spotify layout — separate

## Other dashboard priorities (reconsider)

| Priority | Item |
|----------|------|
| High | Garmin Fenix sync |
| High | Walk badge reliable on refresh |
| Medium | One clear movement source label (pad / Garmin / manual) |
| Low | Startup splash non-blocking on refresh |

## Phases

### Phase 1 — Quick wins
- Per-kind TTL (60s meeting/walk, 8s others)
- Walk → Telegram
- More visible TTL bar + entry animation

### Phase 2 — “It happened”
- Persistent notice strip (1h)
- Log lines for meeting + walk

### Phase 3 — Optional
- Tap to dismiss
- Quiet hours (no walk TTS 22:00–08:00)
- README for settings

## Risks

| Choice | Upside | Downside |
|--------|--------|----------|
| Longer TTL | You see it | Header busy longer |
| Telegram for walk | Phone backup | Can feel naggy |
| Persistent strip | Proof nudge ran | Clutter if many nudges |
| Tap to dismiss | Clear ack | Extra interaction |

**Suggested default:** Phase 1 + Phase 2, **no** tap-to-dismiss yet.

## Success criteria

- You can answer “Did Chili nudge me to walk?” from **strip or Log**, not memory
- Meeting T-10 shows on wall **or** Telegram once per event
- Spotify/voice toasts stay short and subtle

## Implementation checklist

- [ ] Per-kind TTL + walk Telegram
- [ ] Persistent header strip (last important nudge + time)
- [ ] Meeting/walk entries in activity Log
- [ ] Stronger pill visibility (reduced-motion safe)
- [ ] Env settings + README
