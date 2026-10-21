"""Tests for rain handling (Milestone 2).

Tests spec section 6.4 (rain metadata) and 10.5 (rain-constrained sessions).
"""

import unittest
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

from app.domain.rain_handling import (
    assess_rain_risk,
    build_rain_prompt,
    format_rain_warning,
    get_home_alternative,
    is_session_weather_blocked,
    calculate_controllable_adherence,
    RAIN_PROBABILITY_THRESHOLD,
)
from app.domain.weather import TravelDay


class RainRiskAssessmentTests(unittest.TestCase):
    """Tests for rain risk assessment."""
    
    def test_no_risk_clear_weather(self):
        """Test clear weather shows no risk."""
        session_start = datetime(2026, 10, 20, 18, 30, tzinfo=ZoneInfo("Asia/Tokyo"))
        travel_conditions = (
            TravelDay(
                date=date(2026, 10, 20),
                weather_code=0,
                precipitation_mm=0,
                precipitation_probability=10,
            ),
        )
        
        result = assess_rain_risk(
            session_start, 
            travel_conditions,
            timezone_name="Asia/Tokyo",
        )
        
        self.assertFalse(result.at_risk)
        self.assertEqual(result.precipitation_probability, 10)
    
    def test_risk_high_probability(self):
        """Test high precipitation probability triggers risk."""
        session_start = datetime(2026, 10, 20, 18, 30, tzinfo=ZoneInfo("Asia/Tokyo"))
        travel_conditions = (
            TravelDay(
                date=date(2026, 10, 20),
                weather_code=3,
                precipitation_mm=0,
                precipitation_probability=60,
            ),
        )
        
        result = assess_rain_risk(
            session_start,
            travel_conditions,
            timezone_name="Asia/Tokyo",
        )
        
        self.assertTrue(result.at_risk)
        self.assertEqual(result.precipitation_probability, 60)
        self.assertIn("60%", result.message)
    
    def test_risk_current_rain(self):
        """Test current precipitation triggers risk."""
        session_start = datetime(2026, 10, 20, 18, 30, tzinfo=ZoneInfo("Asia/Tokyo"))
        travel_conditions = (
            TravelDay(
                date=date(2026, 10, 20),
                weather_code=61,
                precipitation_mm=5.2,
                precipitation_probability=80,
            ),
        )
        
        result = assess_rain_risk(
            session_start,
            travel_conditions,
            timezone_name="Asia/Tokyo",
        )
        
        self.assertTrue(result.at_risk)
        self.assertIn("5.2mm", result.message)
    
    def test_threshold_boundary(self):
        """Test the 50% threshold boundary."""
        session_start = datetime(2026, 10, 20, 18, 30, tzinfo=ZoneInfo("Asia/Tokyo"))
        
        below_threshold = (
            TravelDay(date=date(2026, 10, 20), precipitation_probability=49),
        )
        result_below = assess_rain_risk(
            session_start, below_threshold, timezone_name="Asia/Tokyo"
        )
        self.assertFalse(result_below.at_risk)
        
        at_threshold = (
            TravelDay(date=date(2026, 10, 20), precipitation_probability=50),
        )
        result_at = assess_rain_risk(
            session_start, at_threshold, timezone_name="Asia/Tokyo"
        )
        self.assertTrue(result_at.at_risk)
    
    def test_no_forecast_data(self):
        """Test handling when no forecast data is available."""
        session_start = datetime(2026, 10, 25, 18, 30, tzinfo=ZoneInfo("Asia/Tokyo"))
        travel_conditions = (
            TravelDay(date=date(2026, 10, 20), precipitation_probability=0),
        )
        
        result = assess_rain_risk(
            session_start,
            travel_conditions,
            timezone_name="Asia/Tokyo",
        )
        
        self.assertFalse(result.at_risk)
        self.assertIn("No forecast", result.message)


class RainPromptTests(unittest.TestCase):
    """Tests for rain warning prompt building."""
    
    def test_build_prompt_has_three_actions(self):
        """Test that prompt has exactly three actions."""
        from app.domain.rain_handling import RainRiskAssessment
        
        assessment = RainRiskAssessment(
            at_risk=True,
            precipitation_probability=70,
            precipitation_mm=0,
            weather_code=3,
            forecast_time=datetime.now(ZoneInfo("Asia/Tokyo")),
            message="Rain probability is 70%",
        )
        
        prompt = build_rain_prompt(
            "session-123",
            "BJJ at Academy",
            datetime(2026, 10, 20, 18, 30, tzinfo=ZoneInfo("Asia/Tokyo")),
            assessment,
        )
        
        self.assertEqual(len(prompt.actions), 3)
        self.assertIn("Move session", prompt.actions)
        self.assertIn("Use home fallback", prompt.actions)
        self.assertIn("Keep original plan", prompt.actions)
    
    def test_format_rain_warning(self):
        """Test rain warning message formatting."""
        from app.domain.rain_handling import RainRiskAssessment
        
        assessment = RainRiskAssessment(
            at_risk=True,
            precipitation_probability=70,
            precipitation_mm=0,
            weather_code=3,
            forecast_time=datetime.now(ZoneInfo("Asia/Tokyo")),
            message="Rain probability is 70%",
        )
        
        prompt = build_rain_prompt(
            "session-123",
            "BJJ at Academy",
            datetime(2026, 10, 20, 18, 30, tzinfo=ZoneInfo("Asia/Tokyo")),
            assessment,
        )
        
        message = format_rain_warning(prompt)
        
        self.assertIn("Rain warning", message)
        self.assertIn("BJJ at Academy", message)
        self.assertIn("Move session", message)
        self.assertIn("home fallback", message.lower())
        self.assertIn("Keep original plan", message)


class HomeAlternativeTests(unittest.TestCase):
    """Tests for home fallback alternatives."""
    
    def test_bjj_alternative(self):
        """Test BJJ session home alternative."""
        alt = get_home_alternative("bjj_normal")
        
        self.assertEqual(alt.alternative_type, "bjj_solo_work")
        self.assertIn("solo", alt.description.lower())
        self.assertIn("NOT a completed BJJ session", alt.counts_as)
    
    def test_bjj_hard_alternative(self):
        """Test BJJ hard session home alternative."""
        alt = get_home_alternative("bjj_hard")
        
        self.assertEqual(alt.alternative_type, "bjj_solo_work")
        self.assertIn("not live rounds", alt.counts_as.lower())
    
    def test_competition_alternative(self):
        """Test competition session home alternative."""
        alt = get_home_alternative("competition")
        
        self.assertEqual(alt.alternative_type, "bjj_solo_work")
    
    def test_strength_alternative(self):
        """Test strength session home alternative."""
        alt = get_home_alternative("strength_a")
        
        self.assertEqual(alt.alternative_type, "strength_home")
        self.assertIn("exercise alternative engine", alt.description.lower())
    
    def test_zone_2_alternative(self):
        """Test zone 2 cardio home alternative."""
        alt = get_home_alternative("zone_2")
        
        self.assertEqual(alt.alternative_type, "cardio_home")
        self.assertIn("WalkingPad", alt.description)
    
    def test_rest_alternative(self):
        """Test rest day alternative."""
        alt = get_home_alternative("rest")
        
        self.assertEqual(alt.alternative_type, "rest")
        self.assertIn("no change", alt.description.lower())


class SessionWeatherBlockedTests(unittest.TestCase):
    """Tests for weather blocked detection."""
    
    def test_weather_blocked_session(self):
        """Test detecting a weather-blocked session."""
        session = {"cancellation_reason": "weather_blocked"}
        self.assertTrue(is_session_weather_blocked(session))
    
    def test_not_weather_blocked(self):
        """Test session that is not weather-blocked."""
        session = {"cancellation_reason": "pain"}
        self.assertFalse(is_session_weather_blocked(session))
    
    def test_no_cancellation(self):
        """Test session with no cancellation reason."""
        session = {"status": "completed"}
        self.assertFalse(is_session_weather_blocked(session))


class ControllableAdherenceTests(unittest.TestCase):
    """Tests for controllable adherence calculation."""
    
    def test_no_weather_blocks(self):
        """Test adherence without weather blocks."""
        result = calculate_controllable_adherence(
            total_sessions=10,
            completed_sessions=8,
            weather_blocked_sessions=0,
        )
        
        self.assertEqual(result["ordinary_adherence"], 80.0)
        self.assertEqual(result["controllable_adherence"], 80.0)
        self.assertFalse(result["has_weather_blocks"])
    
    def test_with_weather_blocks(self):
        """Test adherence with weather blocks.
        
        Per spec: A rain-blocked miss remains in ordinary adherence but is 
        excluded from controllable-adherence failure.
        """
        result = calculate_controllable_adherence(
            total_sessions=10,
            completed_sessions=7,
            weather_blocked_sessions=2,
        )
        
        self.assertEqual(result["ordinary_adherence"], 70.0)
        self.assertEqual(result["controllable_adherence"], 87.5)
        self.assertTrue(result["has_weather_blocks"])
        self.assertEqual(result["weather_blocked_count"], 2)
    
    def test_all_weather_blocked(self):
        """Test when all missed sessions are weather blocked."""
        result = calculate_controllable_adherence(
            total_sessions=5,
            completed_sessions=3,
            weather_blocked_sessions=2,
        )
        
        self.assertEqual(result["ordinary_adherence"], 60.0)
        self.assertEqual(result["controllable_adherence"], 100.0)
    
    def test_zero_sessions(self):
        """Test with zero total sessions."""
        result = calculate_controllable_adherence(
            total_sessions=0,
            completed_sessions=0,
            weather_blocked_sessions=0,
        )
        
        self.assertEqual(result["ordinary_adherence"], 100.0)
        self.assertEqual(result["controllable_adherence"], 100.0)


if __name__ == "__main__":
    unittest.main()
