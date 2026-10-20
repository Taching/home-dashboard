# UAT — Workout library + weekly analyzer (V1)

_Spec: WORKOUT_LIBRARY_AND_WEEKLY_ANALYZER_SPEC v1.2 §19–21.
Scope: M1–M4. Photos / M5 = V2 (out of scope)._

_Last verified: see `scripts/verify_uat_v1.sh` output._

## How to verify

```sh
scripts/verify_uat_v1.sh          # automated + static probes
# On the Pi after deploy (manual smoke):
#   /training/exercises  /workout  /weekly  /schedule-change?prefill=…
```

Pass = all automated checks green. Manual rows need a phone/Tailscale pass after deploy.

---

## Definition of done (spec §21)

| # | Athlete can… | Automated | Manual (Pi) |
| --- | --- | --- | --- |
| 1 | See how every seeded exercise is classified | Seed + classification tests | Browse `/training/exercises` |
| 2 | Ask for a replacement and see why | Alternatives tests | Find alternative on phone |
| 3 | Log BJJ and strength without an essay | Logging + BJJ analysis tests | One gym + one BJJ log |
| 4 | Get one deterministic Mon–Sun weekly review | Weekly analyzer tests | Open `/weekly` |
| 5 | Inspect evidence behind conclusions | Evidence-key tests | Expand evidence on `/weekly` |
| 6 | Ask for harsh AI explanation only on demand | Ask-coach dry-run + static (no auto AI) | Press Ask coach once |
| 7 | Prefill schedule-change without mutating planner | Prefill link static + API | Cancel prefilled change |
| 8 | Handle rain without execution blame / solo≠live BJJ | Rain + controllable adherence tests | Rain prompt when travel BJJ |

---

## §19 Acceptance criteria

### Exercise library

| ID | Criterion | Verify |
| --- | --- | --- |
| EL-1 | Seed inserts exercises + failure tags, no dupes | `test_exercise_library` seed tests |
| EL-2 | Alias search → `landmine-180` | grappler / full-contact / barbell rotation tests |
| EL-3 | Bench = horizontal push; squat ≠ vertical push; deadlift = hinge | classification tests |
| EL-4 | Library has KB / landmine / sled / sprawl / grip / neck coverage | seed coverage tests |
| EL-5 | Risky exercises expose risk note | risk-note test / detail API |

### Alternatives

| ID | Criterion | Verify |
| --- | --- | --- |
| ALT-1 | Equipment required; exclusions honored | alternatives engine tests |
| ALT-2 | Bench / front squat / deadlift / landmine acceptance cases | §8.4 tests |
| ALT-3 | Reasons + tradeoff on results | alternatives response shape |
| ALT-4 | Substitute stores planned + performed slugs | workout logging substitution test |

### Logging and calculations

| ID | Criterion | Verify |
| --- | --- | --- |
| LOG-1 | Compact strength log (no set-by-set page) | logging API + Workout UI (manual) |
| LOG-2 | Compact reps / e1RM same-slug rules | logging + weekly analyzer tests |
| LOG-3 | Plain done holds load | progression / logging tests |
| LOG-4 | Optional BJJ fields; no fake success % | BJJ analysis validation tests |
| LOG-5 | Recurring failures across distinct sessions | weekly analyzer recurrence tests |

### Weekly analyzer + Ask coach

| ID | Criterion | Verify |
| --- | --- | --- |
| WA-1 | Claims have evidence keys; low data → `insufficient_data` | `test_weekly_analyzer` |
| WA-2 | Execution before program blame; recovery softens intensity | analyzer cause-code tests |
| WA-3 | ≤3 actions / ≤3 tests | analyzer shape tests |
| WA-4 | `/weekly` + Monday recompute = zero AI; Ask coach = on-demand | static probe + dry-run coach test |
| WA-5 | Prefill `/schedule-change` only; no auto planner write | WeeklyReviewPage link + coach API |

### Rain handling

| ID | Criterion | Verify |
| --- | --- | --- |
| RAIN-1 | Only `requires_travel` gets rain check | rain-check API + reminder wiring |
| RAIN-2 | ≥50% precip or current rain → three-action prompt | `test_rain_handling` |
| RAIN-3 | Keep / no response leaves session unchanged; `weather_blocked` only after confirm | rain action + cancellation tests |
| RAIN-4 | Weather-blocked excluded from controllable adherence | controllable adherence tests |
| RAIN-5 | Home fallback ≠ academy / live rounds | analyzer weather scenario |

### OpenClaw / surfaces

| ID | Criterion | Verify |
| --- | --- | --- |
| OC-1 | No new Sunday auto AI weekly job | static: no schedule for auto ask-coach |
| OC-2 | Wall stays read-only (no new workout controls) | no-kiosk-restyle rule + static |
| OC-3 | Garmin / preferences never replan | existing product rules (manual) |

### Photos (V2) — N/A

All photo criteria are **out of scope for V1**. Mark N/A until M5.

---

## Manual smoke (after Pi deploy)

1. `/training/exercises` — search `grappler twist` → Landmine 180; open alternatives with limited equipment.
2. `/workout/…` — log compact reps + RPE + technique; optional BJJ focus/failure under ~60s.
3. `/weekly` — facts appear without pressing Ask coach; evidence expands.
4. Press **Ask coach about this week** once — explanation only; **Use in schedule change** opens prefill; cancel leaves plan unchanged.
5. If rain risk on travel BJJ — three actions; Keep original leaves calendar alone.

---

## Result

Automated verdict is printed by `scripts/verify_uat_v1.sh` (`PASS` / `FAIL`).
Record Pi manual smoke separately when deploying.
