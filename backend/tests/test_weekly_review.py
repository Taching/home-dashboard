import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.session import Base
from app.domain.chili_notify import ChiliNotifyService
from app.domain.training_logs import TrainingService
from app.domain.weekly import WeeklyService
from app.jobs.weekly_review import maybe_send_weekly_review


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


class WeeklyReviewJobTests(unittest.TestCase):
    def setUp(self) -> None:
        factory = test_session_factory()
        self.weekly = WeeklyService(session_factory=factory)
        self.training = TrainingService(session_factory=factory)
        self.notify = ChiliNotifyService(session_factory=factory)
        self.openclaw = FakeOpenClaw()
        self.tokyo = ZoneInfo("Asia/Tokyo")

    def test_sends_once_on_monday_morning(self) -> None:
        now = datetime(2026, 11, 2, 10, 4, tzinfo=self.tokyo)
        first = maybe_send_weekly_review(
            weekly=self.weekly,
            notify_service=self.notify,
            openclaw=self.openclaw,
            public_url=self.training.public_url,
            now=now,
        )
        second = maybe_send_weekly_review(
            weekly=self.weekly,
            notify_service=self.notify,
            openclaw=self.openclaw,
            public_url=self.training.public_url,
            now=now,
        )
        self.assertEqual(first, "sent")
        self.assertIsNone(second)
        self.assertEqual(len(self.openclaw.messages), 1)
        self.assertIn("/daily/2026-11-02", self.openclaw.messages[0])
        self.assertIn("Monday check-in", self.openclaw.messages[0])

    def test_skips_after_check_in_is_saved(self) -> None:
        now = datetime(2026, 11, 2, 10, 4, tzinfo=self.tokyo)
        self.weekly.save_weekly(
            now.date(),
            self.training,
            energy=3, hunger=3, bjj_performance=4,
            now=now,
        )
        result = maybe_send_weekly_review(
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
