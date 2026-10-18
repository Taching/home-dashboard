from __future__ import annotations

from datetime import date, datetime, time, timedelta

from app.domain.training.constraints import (
    BJJ_TYPES,
    STRENGTH_TYPES,
    availability_for,
    needs_rest,
    recovery_penalty,
)
from app.domain.training.phases import MARCH_COMPETITION_START, phase_for_date
from app.domain.training.policy import weekly_targets
from app.domain.training.ranker import close_set, deterministic_reason, pick_default, score_session, valid_candidates
from app.domain.training.types import (
    CAMPAIGN_PHASES,
    COMPETITION_PHASES,
    DayPlan,
    RecordStatus,
    RebuildResult,
    SchedulerInput,
    TrainingRecord,
    WorkoutType,
)


def next_strength(history: tuple[TrainingRecord, ...]) -> WorkoutType:
    completed = [
        item.session for item in history
        if item.status == RecordStatus.COMPLETED and item.session in STRENGTH_TYPES
    ]
    if not completed:
        return WorkoutType.STRENGTH_A
    return WorkoutType.STRENGTH_B if completed[-1] == WorkoutType.STRENGTH_A else WorkoutType.STRENGTH_A


def rebuild_schedule(inp: SchedulerInput, *, use_llm: bool = False) -> RebuildResult:
    today = inp.today
    horizon_end = _horizon_end(inp)
    hard_yesterday = any(
        item.date == today - timedelta(days=1)
        and item.status == RecordStatus.COMPLETED
        and item.session == WorkoutType.BJJ_HARD
        for item in inp.history
    )
    penalty = recovery_penalty(inp.athlete_state, completed_hard_yesterday=hard_yesterday)
    missed_bjj = any(
        item.status == RecordStatus.MISSED and item.session in BJJ_TYPES
        for item in inp.history
    )
    hard_bjj_day = inp.upcoming_hard_bjj
    strength_type = next_strength(inp.history)
    days = {item.date: _history_plan(item, penalty) for item in inp.history}

    future_days = [
        today + timedelta(days=offset)
        for offset in range((horizon_end - today).days + 1)
        if today + timedelta(days=offset) not in {item.date for item in inp.history if item.status == RecordStatus.COMPLETED}
    ]
    avail = {day: availability_for(day, inp) for day in future_days}
    protect = True
    if hard_bjj_day is None:
        for day, item in avail.items():
            if item.allows(WorkoutType.BJJ_HARD) and item.bjj_class is not None and item.bjj_class.class_type.value == "COMPETITION":
                hard_bjj_day = day
                break

    assigned: dict[date, WorkoutType | None] = {}
    for day, kind in inp.locked_sessions:
        if day >= today:
            assigned[day] = kind
    strength_remaining = not any(kind in STRENGTH_TYPES for kind in assigned.values())
    grip_remaining = True
    zone2_remaining = True
    extra_rest = bool(inp.adaptation and inp.adaptation.extra_rest_before_hard_bjj)
    reduce_strength = bool(inp.adaptation and inp.adaptation.reduce_preceding_strength)

    campaign_days = [
        day for day in future_days
        if day not in assigned and phase_for_date(day) in CAMPAIGN_PHASES | COMPETITION_PHASES
    ]
    if campaign_days:
        _assign_campaign(campaign_days, assigned, avail, inp, next_type=strength_type)

    for day in future_days:
        if day in assigned:
            continue
        item = avail[day]
        if not item.user_available:
            assigned[day] = None
            continue
        if needs_rest(inp.athlete_state) and day in {today, today + timedelta(days=1)}:
            assigned[day] = WorkoutType.REST
            continue
        allow_strength = strength_remaining
        if reduce_strength and hard_bjj_day is not None and 0 < (hard_bjj_day - day).days <= 2:
            allow_strength = False
        candidates = valid_candidates(
            day, item, inp,
            next_strength=strength_type,
            strength_remaining=allow_strength,
            hard_bjj_day=hard_bjj_day,
            protect_hard=protect,
        )
        if not zone2_remaining:
            candidates = [option for option in candidates if option != WorkoutType.ZONE_2]
        if not grip_remaining:
            candidates = [option for option in candidates if option != WorkoutType.GRIP]
        if hard_bjj_day == day and WorkoutType.BJJ_HARD in candidates:
            if _slot_already_ended(day, WorkoutType.BJJ_HARD, inp):
                assigned[day] = None
            else:
                assigned[day] = WorkoutType.BJJ_HARD
            continue
        if hard_bjj_day is not None and day == hard_bjj_day - timedelta(days=1):
            assigned[day] = WorkoutType.REST if WorkoutType.REST in candidates else (
                WorkoutType.ZONE_2 if WorkoutType.ZONE_2 in candidates else WorkoutType.REST
            )
            continue
        if extra_rest and hard_bjj_day is not None and day == hard_bjj_day - timedelta(days=2):
            if WorkoutType.BJJ_HARD not in candidates and WorkoutType.BJJ_NORMAL not in candidates:
                assigned[day] = WorkoutType.REST
                continue
        if candidates == [WorkoutType.REST]:
            assigned[day] = None
            continue
        scores = {session: score_session(session, day, inp, hard_bjj_day=hard_bjj_day, missed_bjj=missed_bjj) for session in candidates}
        chosen = pick_default(candidates, scores)
        if _slot_already_ended(day, chosen, inp):
            assigned[day] = None
            continue
        if chosen in STRENGTH_TYPES:
            strength_remaining = False
        if chosen == WorkoutType.GRIP:
            grip_remaining = False
        if chosen == WorkoutType.ZONE_2:
            zone2_remaining = False
        assigned[day] = chosen

    if not strength_remaining:
        pass
    else:
        for day in future_days:
            if assigned.get(day) in STRENGTH_TYPES:
                strength_remaining = False
                break

    # Keep distinct fallback work on BJJ-gym closure days. On ordinary days,
    # avoid filling open calendar space with extra low-priority sessions.
    closure_days = {day for day, item in avail.items() if not item.gym_open}
    _drop_extra_accessories(assigned, [day for day in future_days if day not in campaign_days], closure_days)

    for day in future_days:
        item = avail[day]
        session = assigned.get(day)
        candidates = valid_candidates(
            day, item, inp,
            next_strength=strength_type if session in STRENGTH_TYPES or session is None else None,
            strength_remaining=session in STRENGTH_TYPES,
            hard_bjj_day=hard_bjj_day,
            protect_hard=protect,
        )
        if session is not None and session not in candidates and session != WorkoutType.REST:
            candidates = [session, *candidates]
        scores = {option: score_session(option, day, inp, hard_bjj_day=hard_bjj_day, missed_bjj=missed_bjj) for option in candidates}
        reason = deterministic_reason(session, day, inp, item.blocked, missed_bjj=missed_bjj, hard_bjj_day=hard_bjj_day)
        close = close_set(candidates, scores, session)
        if use_llm and session is not None and len(close) > 1:
            from app.domain.training.llm import rerank_and_explain
            picked, explained = rerank_and_explain(close, session, reason, inp, day)
            if picked in close:
                session = picked
                reason = explained
        days[day] = DayPlan(
            session=session,
            recovery_penalty=penalty,
            reason=reason,
            blocked=item.blocked,
            close_set=close,
            status="planned",
        )
    return RebuildResult(days)


# Default BJJ days when the week needs fewer sessions than there are classes:
# Saturday competition class first, then Mon / Wed (Thu as the fourth), which
# leaves Tue/Thu for Strength A/B and Friday as rest before Saturday.
BJJ_WEEKDAY_PREFERENCE = (5, 0, 2, 3, 1, 4, 6)


def _assign_campaign(
    days: list[date],
    assigned: dict[date, WorkoutType | None],
    avail: dict,
    inp: SchedulerInput,
    *,
    next_type: WorkoutType,
) -> None:
    """March 2027 plan as per-week quotas instead of "best session per day".

    BJJ fills the weekly target (calendar-confirmed BJJ always counts and always
    stays), Strength A/B alternate up to the target on non-adjacent days and
    never the day before hard BJJ, easy cardio fills what is left only while the
    week keeps its full rest day. A skipped lift counts as decided for the week;
    a missed BJJ class may be replaced on a later class day."""
    weeks: dict[date, list[date]] = {}
    for day in days:
        weeks.setdefault(day - timedelta(days=day.weekday()), []).append(day)
    pinned = dict(inp.pinned_bjj)
    for week_start, week_days in sorted(weeks.items()):
        week_days.sort()
        week = [week_start + timedelta(days=offset) for offset in range(7)]
        targets = dict(weekly_targets(phase_for_date(week_start)))
        if week_start <= MARCH_COMPETITION_START < week_start + timedelta(days=7):
            targets.update(bjj=2, strength=1, zone_2=0)
        logged = [item for item in inp.history if item.date in week]
        bjj_left = targets["bjj"] - sum(
            item.status == RecordStatus.COMPLETED and item.session in BJJ_TYPES for item in logged
        ) - sum(assigned.get(day) in BJJ_TYPES for day in week)
        strength_left = targets["strength"] - sum(item.session in STRENGTH_TYPES for item in logged) - sum(
            assigned.get(day) in STRENGTH_TYPES for day in week
        )
        zone2_left = targets["zone_2"] - sum(
            item.status == RecordStatus.COMPLETED and item.session == WorkoutType.ZONE_2 for item in logged
        ) - sum(assigned.get(day) == WorkoutType.ZONE_2 for day in week)

        def open_days() -> list[date]:
            return [day for day in week_days if day not in assigned]

        for day in open_days():
            if phase_for_date(day) in COMPETITION_PHASES:
                assigned[day] = WorkoutType.COMPETITION
            elif day + timedelta(days=1) == MARCH_COMPETITION_START:
                assigned[day] = WorkoutType.REST
            elif not avail[day].user_available:
                assigned[day] = None
            elif needs_rest(inp.athlete_state) and day in {inp.today, inp.today + timedelta(days=1)}:
                assigned[day] = WorkoutType.REST
        for day in open_days():
            kind = pinned.get(day)
            if kind is not None and avail[day].allows(WorkoutType.BJJ_NORMAL):
                assigned[day] = kind if avail[day].allows(kind) else WorkoutType.BJJ_NORMAL
                bjj_left -= 1

        bjj_options = [
            day for day in open_days()
            if avail[day].allows(WorkoutType.BJJ_NORMAL) and not _slot_already_ended(day, WorkoutType.BJJ_NORMAL, inp)
        ]
        bjj_options.sort(key=lambda day: (
            not avail[day].allows(WorkoutType.BJJ_HARD), BJJ_WEEKDAY_PREFERENCE.index(day.weekday()), day,
        ))
        for day in bjj_options[:max(0, bjj_left)]:
            assigned[day] = WorkoutType.BJJ_HARD if avail[day].allows(WorkoutType.BJJ_HARD) else WorkoutType.BJJ_NORMAL

        hard_days = {day for day, kind in assigned.items() if kind == WorkoutType.BJJ_HARD}
        hard_days |= {day for day, kind in pinned.items() if kind == WorkoutType.BJJ_HARD}
        if inp.upcoming_hard_bjj is not None:
            hard_days.add(inp.upcoming_hard_bjj)
        for day in open_days():
            if day + timedelta(days=1) in hard_days:
                assigned[day] = WorkoutType.REST

        strength_days = {item.date for item in inp.history if item.session in STRENGTH_TYPES}
        strength_days |= {day for day, kind in assigned.items() if kind in STRENGTH_TYPES}
        for day in open_days():
            if strength_left <= 0:
                break
            if not avail[day].allows(next_type) or _slot_already_ended(day, next_type, inp):
                continue
            if day - timedelta(days=1) in strength_days or day + timedelta(days=1) in strength_days:
                continue
            assigned[day] = next_type
            strength_days.add(day)
            strength_left -= 1
            next_type = WorkoutType.STRENGTH_B if next_type == WorkoutType.STRENGTH_A else WorkoutType.STRENGTH_A

        trained = {item.date for item in logged if item.status == RecordStatus.COMPLETED}

        def rest_days() -> int:
            return sum(
                1 for day in week
                if day not in trained and assigned.get(day, None) in {None, WorkoutType.REST}
            )

        for day in open_days():
            if zone2_left <= 0:
                break
            if not avail[day].allows(WorkoutType.ZONE_2) or _slot_already_ended(day, WorkoutType.ZONE_2, inp):
                continue
            if rest_days() - 1 < targets["rest"]:
                break
            assigned[day] = WorkoutType.ZONE_2
            zone2_left -= 1
        for day in open_days():
            assigned[day] = None


def _history_plan(record: TrainingRecord, penalty: float) -> DayPlan:
    return DayPlan(
        session=record.session,
        recovery_penalty=penalty,
        reason="Completed training stays as logged." if record.status == RecordStatus.COMPLETED else (
            f"Missed {record.session.value}" + (f" ({record.miss_reason.value})" if record.miss_reason else "") + "."
        ),
        status="completed" if record.status == RecordStatus.COMPLETED else "missed",
    )


def _horizon_end(inp: SchedulerInput) -> date:
    end = inp.today + timedelta(days=max(0, inp.horizon_days - 1))
    extras = [inp.upcoming_hard_bjj, inp.tournament_date]
    extras.extend(item.date for item in inp.gym_availability)
    extras.extend(item.date for item in inp.class_availability)
    extras.extend(inp.unavailability)
    known = [item for item in extras if item is not None]
    if known:
        end = max(end, max(known))
    return end


def _drop_extra_accessories(
    assigned: dict[date, WorkoutType | None],
    days: list[date],
    closure_days: set[date],
) -> None:
    accessories = [day for day in days if assigned.get(day) in {WorkoutType.GRIP, WorkoutType.ZONE_2}]
    ordinary_accessories = [day for day in accessories if day not in closure_days]
    if len(ordinary_accessories) <= 1:
        return
    for day in ordinary_accessories[1:]:
        assigned[day] = None


def _slot_already_ended(day: date, session: WorkoutType | None, inp: SchedulerInput) -> bool:
    if session is None or inp.as_of is None:
        return False
    if session in {WorkoutType.REST, WorkoutType.RECOVERY, WorkoutType.COMPETITION}:
        return False
    start_clock = time(10, 0) if day.weekday() == 5 and session in BJJ_TYPES else time(7, 30)
    duration = {
        WorkoutType.STRENGTH_A: 60,
        WorkoutType.STRENGTH_B: 55,
        WorkoutType.ZONE_2: 45,
        WorkoutType.GRIP: 15,
    }.get(session, 90)
    start = datetime.combine(day, start_clock, tzinfo=inp.as_of.tzinfo)
    return inp.as_of >= start + timedelta(minutes=duration)
