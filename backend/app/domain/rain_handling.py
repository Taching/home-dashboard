"""Rain handling for leave-home training sessions.

Implements spec section 6.4 (rain metadata) and 10.5 (rain-constrained sessions).
Milestone 2 scope.

Key rules from spec:
- Rain is an actual availability constraint, not mere weather context
- Weather never silently cancels or moves a session
- weather_blocked is stored only after explicit athlete confirmation
- A rain-blocked miss is NOT an execution failure
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from app.core.settings import settings
from app.domain.weather import TravelDay


RainAction = Literal["move_session", "use_home_fallback", "keep_original_plan"]

RAIN_PROBABILITY_THRESHOLD = 50


@dataclass
class RainRiskAssessment:
    """Assessment of rain risk for a session requiring travel."""
    at_risk: bool
    precipitation_probability: float
    precipitation_mm: float
    weather_code: int
    forecast_time: datetime
    message: str


@dataclass
class RainPrompt:
    """Rain warning prompt for the athlete."""
    session_id: str
    session_title: str
    session_start: datetime
    assessment: RainRiskAssessment
    actions: tuple[str, str, str]


@dataclass
class HomeAlternative:
    """Home fallback for a rain-blocked session."""
    original_session_type: str
    alternative_type: str
    description: str
    counts_as: str


def assess_rain_risk(
    session_start: datetime,
    travel_conditions: tuple[TravelDay, ...],
    *,
    departure_buffer_minutes: int = 30,
    timezone_name: str | None = None,
) -> RainRiskAssessment:
    """Assess rain risk for a session requiring travel.
    
    Per spec section 10.5:
    - Rain at risk when precipitation currently reported OR 
      hourly precipitation probability >= 50% during travel window
    """
    tz = ZoneInfo(timezone_name or settings.timezone)
    departure_time = session_start - timedelta(minutes=departure_buffer_minutes)
    departure_date = departure_time.astimezone(tz).date()
    
    matching_day = None
    for day in travel_conditions:
        if day.date == departure_date:
            matching_day = day
            break
    
    if matching_day is None:
        return RainRiskAssessment(
            at_risk=False,
            precipitation_probability=0,
            precipitation_mm=0,
            weather_code=0,
            forecast_time=datetime.now(tz),
            message="No forecast data available for this date.",
        )
    
    at_risk = (
        matching_day.precipitation_mm > 0 or
        matching_day.precipitation_probability >= RAIN_PROBABILITY_THRESHOLD
    )
    
    if at_risk:
        if matching_day.precipitation_mm > 0:
            message = (
                f"Rain reported ({matching_day.precipitation_mm:.1f}mm). "
                f"Precipitation probability: {matching_day.precipitation_probability:.0f}%."
            )
        else:
            message = (
                f"Rain probability is {matching_day.precipitation_probability:.0f}% "
                f"for your travel time."
            )
    else:
        message = "Weather looks clear for travel."
    
    return RainRiskAssessment(
        at_risk=at_risk,
        precipitation_probability=matching_day.precipitation_probability,
        precipitation_mm=matching_day.precipitation_mm,
        weather_code=matching_day.weather_code,
        forecast_time=datetime.now(tz),
        message=message,
    )


def build_rain_prompt(
    session_id: str,
    session_title: str,
    session_start: datetime,
    assessment: RainRiskAssessment,
) -> RainPrompt:
    """Build rain warning prompt with three actions.
    
    Per spec: The pre-workout message offers exactly three actions:
    - Move session
    - Use home fallback  
    - Keep original plan
    
    No response leaves the plan unchanged.
    """
    return RainPrompt(
        session_id=session_id,
        session_title=session_title,
        session_start=session_start,
        assessment=assessment,
        actions=(
            "Move session",
            "Use home fallback",
            "Keep original plan",
        ),
    )


def get_home_alternative(session_type: str) -> HomeAlternative:
    """Get the default home alternative for a rain-blocked session.
    
    Per spec table:
    - BJJ at academy → solo drills/movement (NOT live BJJ)
    - Strength away from home → rebuild with home equipment
    - Easy outdoor cardio → indoor option
    - Rest → no change
    """
    session_type_lower = session_type.lower()
    
    if "bjj" in session_type_lower or session_type_lower == "competition":
        return HomeAlternative(
            original_session_type=session_type,
            alternative_type="bjj_solo_work",
            description=(
                "20–30 minutes of solo grappling movement/position drills, "
                "or easy indoor cardio when no safe drill space exists."
            ),
            counts_as=(
                "Useful skill/conditioning work, but NOT a completed BJJ session "
                "and not live rounds."
            ),
        )
    
    if "strength" in session_type_lower:
        return HomeAlternative(
            original_session_type=session_type,
            alternative_type="strength_home",
            description=(
                "Rebuild the session from the exercise alternative engine "
                "using only equipment marked available at home."
            ),
            counts_as=(
                "Counts as strength only if the required work is completed."
            ),
        )
    
    if "zone" in session_type_lower or "cardio" in session_type_lower:
        return HomeAlternative(
            original_session_type=session_type,
            alternative_type="cardio_home",
            description=(
                "WalkingPad, indoor bike, rower, or another available "
                "easy indoor option at the same intended effort."
            ),
            counts_as="Counts as the planned easy-cardio session.",
        )
    
    return HomeAlternative(
        original_session_type=session_type,
        alternative_type="rest",
        description="No change — rest as planned.",
        counts_as="Remains rest.",
    )


def format_rain_warning(prompt: RainPrompt) -> str:
    """Format rain warning message for the pre-workout notification.
    
    This is appended to the existing pre-workout message, not a new notification.
    """
    lines = [
        f"⚠️ **Rain warning** for {prompt.session_title}:",
        prompt.assessment.message,
        "",
        "Choose one:",
        f"1. **Move session** — reschedule within this week",
        f"2. **Use home fallback** — work out at home instead",
        f"3. **Keep original plan** — go anyway",
        "",
        "No response will keep the original plan.",
    ]
    return "\n".join(lines)


def is_session_weather_blocked(session: dict) -> bool:
    """Check if a session was cancelled due to weather.
    
    This distinguishes a confirmed rain block from an execution miss.
    """
    return session.get("cancellation_reason") == "weather_blocked"


def calculate_controllable_adherence(
    total_sessions: int,
    completed_sessions: int,
    weather_blocked_sessions: int,
) -> dict:
    """Calculate both ordinary and controllable adherence.
    
    Per spec: A rain-blocked miss remains in ordinary adherence but is 
    excluded from controllable-adherence failure.
    
    Returns both percentages when at least one session was weather-blocked.
    """
    if total_sessions == 0:
        return {
            "ordinary_adherence": 100.0,
            "controllable_adherence": 100.0,
            "has_weather_blocks": False,
        }
    
    controllable_total = total_sessions - weather_blocked_sessions
    
    ordinary = (completed_sessions / total_sessions) * 100
    controllable = (
        (completed_sessions / controllable_total) * 100 
        if controllable_total > 0 
        else 100.0
    )
    
    return {
        "ordinary_adherence": round(ordinary, 1),
        "controllable_adherence": round(controllable, 1),
        "has_weather_blocks": weather_blocked_sessions > 0,
        "weather_blocked_count": weather_blocked_sessions,
    }
