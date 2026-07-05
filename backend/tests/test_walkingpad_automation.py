import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.router import api_router
from app.database.session import Base
from app.domain.activity_feed import ActivityFeedService
from app.domain.walkingpad import WalkingPadService


def test_session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


class FakeOpenClaw:
    def configured(self) -> bool:
        return True

    def send(self, message: str) -> dict[str, str | None]:
        return {"delivery_status": "started", "reply": None}


class WalkingPadAutomationApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = FastAPI()
        self.app.include_router(api_router, prefix="/api/v1")
        self.app.state.activity_feed_service = ActivityFeedService()
        self.app.state.walkingpad_service = WalkingPadService(
            session_factory=test_session_factory(),
            bridge_token="bridge-token",
        )
        self.app.state.openclaw_service = FakeOpenClaw()
        self.client = TestClient(self.app)
        self.token = "automation-token"

    @patch("app.api.router.settings")
    def test_automation_log_accepts_structured_payload(self, settings) -> None:
        settings.dashboard_automation_token = self.token
        response = self.client.post(
            "/api/v1/automation/walkingpad/log",
            headers={"Authorization": f"Bearer {self.token}"},
            json={"duration_minutes": 30, "distance_km": 2},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "logged")
        self.assertEqual(body["today"]["total_minutes"], 30.0)
        self.assertEqual(body["today"]["total_distance_km"], 2.0)

    @patch("app.api.router.settings")
    def test_openclaw_chat_logs_walk_without_sending(self, settings) -> None:
        settings.dashboard_automation_token = self.token
        response = self.client.post(
            "/api/v1/openclaw/messages",
            json={"message": "I walked 20 min and 1.5 km today"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "success")
        self.assertIn("Logged walk", body["reply"] or "")


if __name__ == "__main__":
    unittest.main()
