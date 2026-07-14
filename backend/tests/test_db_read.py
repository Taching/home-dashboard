import unittest
from datetime import UTC, datetime
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.router import api_router
from app.database.models import SensorReading, WalkingPadSession
from app.database.session import Base
from app.domain.db_read import DbReadService


def test_session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


class DbReadServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.factory = test_session_factory()
        self.service = DbReadService(session_factory=self.factory, timezone_name="Asia/Tokyo")
        with self.factory() as session:
            session.add_all(
                [
                    SensorReading(
                        recorded_at=datetime(2026, 7, 13, 1, 0, tzinfo=UTC),
                        temperature_c=24.0,
                        humidity_percent=50.0,
                    ),
                    WalkingPadSession(
                        external_id="walk-1",
                        started_at=datetime(2026, 7, 13, 2, 0, tzinfo=UTC),
                        ended_at=datetime(2026, 7, 13, 3, 0, tzinfo=UTC),
                        duration_seconds=3600,
                        distance_km=4.0,
                        steps=6500,
                        calories=250.0,
                    ),
                ]
            )
            session.commit()

    def test_day_snapshot_includes_walk_steps(self) -> None:
        snapshot = self.service.snapshot_for_date(datetime(2026, 7, 13, tzinfo=UTC).date())
        # 2026-07-13 UTC morning is still 2026-07-13 in JST for these timestamps
        self.assertEqual(snapshot["summary"]["walk_total_steps"], 6500)
        self.assertEqual(snapshot["summary"]["walk_session_count"], 1)
        self.assertEqual(len(snapshot["sensor_readings"]), 1)

    def test_rejects_inverted_range(self) -> None:
        with self.assertRaises(ValueError):
            self.service.snapshot_for_range(
                datetime(2026, 7, 14).date(),
                datetime(2026, 7, 13).date(),
            )


class DbReadApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.factory = test_session_factory()
        self.app = FastAPI()
        self.app.include_router(api_router, prefix="/api/v1")
        self.app.state.db_read_service = DbReadService(
            session_factory=self.factory,
            timezone_name="Asia/Tokyo",
        )
        self.client = TestClient(self.app)
        self.token = "automation-token"
        with self.factory() as session:
            session.add(
                WalkingPadSession(
                    external_id="walk-api",
                    started_at=datetime(2026, 7, 12, 3, 0, tzinfo=UTC),
                    ended_at=datetime(2026, 7, 12, 4, 0, tzinfo=UTC),
                    duration_seconds=3600,
                    distance_km=3.5,
                    steps=5000,
                    calories=200.0,
                )
            )
            session.commit()

    def test_requires_auth(self) -> None:
        response = self.client.get("/api/v1/db/2026-07-12")
        self.assertEqual(response.status_code, 401)

    def test_day_query(self) -> None:
        with patch("app.api.router.settings") as settings:
            settings.dashboard_automation_token = self.token
            response = self.client.get(
                "/api/v1/db/2026-07-12",
                headers={"Authorization": f"Bearer {self.token}"},
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["start_date"], "2026-07-12")
        self.assertEqual(body["end_date"], "2026-07-12")
        self.assertEqual(body["summary"]["walk_total_steps"], 5000)

    def test_days_range_query(self) -> None:
        with patch("app.api.router.settings") as settings:
            settings.dashboard_automation_token = self.token
            response = self.client.get(
                "/api/v1/db/2026-07-10?days=7",
                headers={"Authorization": f"Bearer {self.token}"},
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["start_date"], "2026-07-10")
        self.assertEqual(body["end_date"], "2026-07-16")


if __name__ == "__main__":
    unittest.main()
