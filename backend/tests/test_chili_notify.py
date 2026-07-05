import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.router import api_router
from app.database.session import Base
from app.domain.activity_feed import ActivityFeedService
from app.domain.chili_notify import ChiliNotifyService


class FakeOpenClaw:
    def __init__(self, configured: bool = True) -> None:
        self.configured_flag = configured
        self.sent: list[str] = []

    def configured(self) -> bool:
        return self.configured_flag

    def send(self, message: str) -> dict[str, str | None]:
        self.sent.append(message)
        return {"delivery_status": "started", "reply": None}


def test_session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


class ChiliNotifyServiceTests(unittest.TestCase):
    def test_dedupe_key_blocks_repeat_within_ttl(self):
        service = ChiliNotifyService(test_session_factory(), ttl_seconds=3600)

        self.assertTrue(service.should_send("meeting:abc:2026-07-05"))
        service.mark_sent("meeting:abc:2026-07-05")
        self.assertFalse(service.should_send("meeting:abc:2026-07-05"))
        self.assertTrue(service.should_send("meeting:def:2026-07-05"))

    def test_release_allows_retry_after_failed_send(self):
        service = ChiliNotifyService(test_session_factory(), ttl_seconds=3600)

        self.assertTrue(service.should_send("meeting:abc:2026-07-05"))
        self.assertFalse(service.should_send("meeting:abc:2026-07-05"))
        service.release("meeting:abc:2026-07-05")
        self.assertTrue(service.should_send("meeting:abc:2026-07-05"))


class ChiliNotifyApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = FastAPI()
        self.app.include_router(api_router, prefix="/api/v1")
        self.app.state.activity_feed_service = ActivityFeedService()
        self.app.state.chili_notify_service = ChiliNotifyService(test_session_factory())
        self.app.state.openclaw_service = FakeOpenClaw()
        self.client = TestClient(self.app)

    def test_notify_sends_message_when_openclaw_configured(self):
        response = self.client.post(
            "/api/v1/chili/notify",
            json={"message": "Mango Standup starts in 10 minutes", "dedupe_key": "meeting:1:2026-07-05"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "sent")
        self.assertEqual(
            self.app.state.openclaw_service.sent,
            ["Mango Standup starts in 10 minutes"],
        )

    def test_notify_skips_duplicate_dedupe_key(self):
        payload = {"message": "Mango Standup starts in 10 minutes", "dedupe_key": "meeting:1:2026-07-05"}
        first = self.client.post("/api/v1/chili/notify", json=payload)
        second = self.client.post("/api/v1/chili/notify", json=payload)

        self.assertEqual(first.json()["status"], "sent")
        self.assertEqual(second.json()["status"], "skipped")
        self.assertEqual(len(self.app.state.openclaw_service.sent), 1)

    def test_notify_reports_not_configured(self):
        self.app.state.openclaw_service = FakeOpenClaw(configured=False)
        response = self.client.post(
            "/api/v1/chili/notify",
            json={"message": "Reminder", "dedupe_key": "meeting:2:2026-07-05"},
        )

        self.assertEqual(response.json()["status"], "not_configured")

    def test_notify_not_configured_does_not_consume_dedupe_key(self):
        payload = {"message": "Reminder", "dedupe_key": "meeting:2:2026-07-05"}
        self.app.state.openclaw_service = FakeOpenClaw(configured=False)
        not_configured = self.client.post("/api/v1/chili/notify", json=payload)
        self.app.state.openclaw_service = FakeOpenClaw(configured=True)
        sent = self.client.post("/api/v1/chili/notify", json=payload)

        self.assertEqual(not_configured.json()["status"], "not_configured")
        self.assertEqual(sent.json()["status"], "sent")


if __name__ == "__main__":
    unittest.main()
