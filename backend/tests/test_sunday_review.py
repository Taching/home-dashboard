import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.session import Base
from app.domain.chili_notify import ChiliNotifyService
from app.domain.training import TrainingService
from app.domain.weekly import WeeklyService
from app.jobs.sunday_review import maybe_send_sunday_review


def test_session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


class FakeOpenClaw:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def configured(self) -> bool:
        return True

    def notify_user(self, message: str) -> dict[str, str]:
        self.messages.append(message)
        return {"delivery_status": "sent"}


class SundayReviewJobTests(unittest.TestCase):
    def setUp(self) -> None:
        factory = test_session_factory()
        self.weekly = WeeklyService(session_factory=factory)
        self.training = TrainingService(session_factory=factory)
        self.notify = ChiliNotifyService(session_factory=factory)
        self.openclaw = FakeOpenClaw()
        self.tokyo = ZoneInfo("Asia/Tokyo")

    def test_sends_once_on_sunday_morning(self) -> None:
        now = datetime(2026, 9, 13, 10, 4, tzinfo=self.tokyo)
        first = maybe_send_sunday_review(
            weekly=self.weekly,
            notify_service=self.notify,
            openclaw=self.openclaw,
            public_url=self.training.public_url,
            now=now,
        )
        second = maybe_send_sunday_review(
            weekly=self.weekly,
            notify_service=self.notify,
            openclaw=self.openclaw,
            public_url=self.training.public_url,
            now=now,
        )
        self.assertEqual(first, "sent")
        self.assertIsNone(second)
        self.assertEqual(len(self.openclaw.messages), 1)
        self.assertIn("/daily/2026-09-13", self.openclaw.messages[0])
        self.assertIn("weigh-in", self.openclaw.messages[0])

    def test_skips_after_sunday_is_saved(self) -> None:
        now = datetime(2026, 9, 13, 10, 4, tzinfo=self.tokyo)
        self.weekly.save_sunday(
            now.date(),
            self.training,
            weight_kg=82.4,
            now=now,
        )
        result = maybe_send_sunday_review(
            weekly=self.weekly,
            notify_service=self.notify,
            openclaw=self.openclaw,
            public_url=self.training.public_url,
            now=now,
        )
        self.assertIsNone(result)
        self.assertEqual(self.openclaw.messages, [])


if __name__ == "__main__":
    unittest.main()
