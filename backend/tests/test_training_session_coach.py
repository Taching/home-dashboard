import unittest
from datetime import UTC, date, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.router import api_router
from app.database.session import Base
from app.domain.training.service import TrainingService
from app.domain.training_preferences import TrainingPreferencesService


def factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


class FakeOpenClaw:
    def __init__(self, reply: str | None = "Solid zone 2 run, keep it easy tomorrow.", raises: bool = False):
        self._reply = reply
        self._raises = raises
        self.last_message: str | None = None

    def configured(self) -> bool:
        return True

    def send(self, message: str) -> dict:
        self.last_message = message
        if self._raises:
            raise RuntimeError("gateway unreachable")
        return {"reply": self._reply, "delivery_status": "completed"}


class NotConfiguredOpenClaw:
    def configured(self) -> bool:
        return False


class CoachReviewApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.factory = factory()
        self.now = datetime(2026, 9, 13, 3, tzinfo=UTC)
        self.training = TrainingService(self.factory, timezone_name="Asia/Tokyo")
        self.training.bootstrap(self.now)
        self.app = FastAPI()
        self.app.include_router(api_router, prefix="/api/v1")
        self.app.state.training_service = self.training
        self.app.state.training_preferences_service = TrainingPreferencesService(self.factory)
        self.client = TestClient(self.app)

    def _log_zone2_session(self, note: str) -> str:
        session = self.training.schedule_gym(date(2026, 9, 13), "strength_a", now=self.now)
        session = self.training.replace_session(session["id"], "zone_2", now=self.now)
        self.training.log_session_result(
            session["id"], status="completed", notes=note, cardio="conversational", now=self.now,
        )
        return session["id"]

    def test_404_when_session_does_not_exist(self) -> None:
        response = self.client.post("/api/v1/training/sessions/does-not-exist/coach")
        self.assertEqual(response.status_code, 404)

    def test_400_when_session_has_no_logged_result_yet(self) -> None:
        session = self.training.schedule_gym(date(2026, 9, 13), "strength_a", now=self.now)
        response = self.client.post(f"/api/v1/training/sessions/{session['id']}/coach")
        self.assertEqual(response.status_code, 400)

    def test_success_path_uses_openclaw_reply(self) -> None:
        session_id = self._log_zone2_session("Ran 5k outdoors, felt easy and good.")
        self.app.state.openclaw_service = FakeOpenClaw(reply="Nice easy 5k — legs are fresh for tomorrow.")
        response = self.client.post(f"/api/v1/training/sessions/{session_id}/coach")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["source"], "openclaw")
        self.assertIn("5k", body["advice"])

    def test_falls_back_to_local_review_when_openclaw_not_configured(self) -> None:
        session_id = self._log_zone2_session("Ran 5k outdoors, felt easy and good.")
        self.app.state.openclaw_service = NotConfiguredOpenClaw()
        response = self.client.post(f"/api/v1/training/sessions/{session_id}/coach")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["source"], "local")

    def test_falls_back_to_local_review_when_openclaw_raises(self) -> None:
        session_id = self._log_zone2_session("Ran 5k outdoors, felt easy and good.")
        self.app.state.openclaw_service = FakeOpenClaw(raises=True)
        response = self.client.post(f"/api/v1/training/sessions/{session_id}/coach")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["source"], "local")

    def test_preferences_are_included_in_the_prompt(self) -> None:
        session_id = self._log_zone2_session("Ran 5k outdoors, felt easy and good.")
        self.app.state.training_preferences_service.save("Bad right knee, avoid hard downhill running.")
        fake = FakeOpenClaw()
        self.app.state.openclaw_service = fake
        response = self.client.post(f"/api/v1/training/sessions/{session_id}/coach")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("Bad right knee", fake.last_message)


if __name__ == "__main__":
    unittest.main()
