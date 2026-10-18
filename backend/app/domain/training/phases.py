from __future__ import annotations

from datetime import date, timedelta

from app.domain.training.types import TrainingPhase

OCTOBER_COMPETITION_START = date(2026, 10, 10)
OCTOBER_COMPETITION_END = date(2026, 10, 11)
# 21st All Japan Master Jiu-Jitsu Championship, Takasaki Arena.
MARCH_COMPETITION_START = date(2027, 3, 5)
MARCH_COMPETITION_END = date(2027, 3, 7)
# Final six weeks (4 BJJ/week, 2-set strength) and the 10–14 day taper.
MARCH_PEAK_START = MARCH_COMPETITION_START - timedelta(weeks=6)
MARCH_TAPER_START = date(2027, 2, 21)


def phase_for_date(day: date) -> TrainingPhase:
    if day <= date(2026, 10, 4):
        return TrainingPhase.BUILD_1
    if day < OCTOBER_COMPETITION_START:
        return TrainingPhase.TAPER_1
    if day <= OCTOBER_COMPETITION_END:
        return TrainingPhase.COMPETITION_1
    if day <= date(2026, 10, 14):
        return TrainingPhase.RECOVERY_1
    if day < MARCH_PEAK_START:
        return TrainingPhase.BUILD_3
    if day < MARCH_TAPER_START:
        return TrainingPhase.PEAK_3
    if day < MARCH_COMPETITION_START:
        return TrainingPhase.TAPER_3
    if day <= MARCH_COMPETITION_END:
        return TrainingPhase.COMPETITION_3
    return TrainingPhase.POST_COMPETITION


def bjj_round_target(day: date) -> tuple[int, int]:
    if day <= date(2026, 9, 20):
        return 3, 120
    if day <= date(2026, 9, 27):
        return 4, 120
    if day <= date(2026, 10, 4):
        return 5, 90
    if day <= date(2026, 10, 10):
        return 3, 120
    if day <= date(2026, 10, 18):
        return 3, 120
    phase = phase_for_date(day)
    if phase == TrainingPhase.BUILD_3:
        # First four weeks of the cut: build rounds back up, no extra intensity.
        return (4, 120) if day < date(2026, 11, 16) else (5, 90)
    if phase == TrainingPhase.PEAK_3:
        return 5, 90
    return 3, 120
