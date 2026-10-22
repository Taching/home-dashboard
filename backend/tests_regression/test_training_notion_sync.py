import unittest
from datetime import UTC, date, datetime, timedelta
from unittest.mock import patch

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import models  # noqa: F401
from app.database.models import TrainingSession
from app.database.session import Base
from app.domain.training.notion_sync import TrainingNotionSync

TRASHED = {"object": "error", "status": 400, "code": "validation_error",
           "message": "Can't edit block that is archived. You must unarchive the block before editing."}


def _row(session_id: str, status: str, page_id: str | None, start: datetime) -> TrainingSession:
    return TrainingSession(
        id=session_id, planned_type="bjj_normal", status=status, phase="build_march",
        planned_week_start=date(2026, 10, 19),
        start_at=start, end_at=start + timedelta(minutes=90), is_all_day=False,
        estimated_minutes=90, intensity="normal", reason="test", source="scheduler",
        pinned=False, revision=1, created_at=start, updated_at=start, notion_page_id=page_id,
    )


class TrainingNotionSyncTests(unittest.TestCase):
    def setUp(self):
        self.dry_run_patcher = patch("app.domain.training.notion_sync.is_dry_run", return_value=False)
        self.dry_run_patcher.start()
        self.addCleanup(self.dry_run_patcher.stop)

    def test_cancelled_session_whose_page_is_gone_does_not_block_the_batch(self) -> None:
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        start = datetime(2026, 10, 19, 22, 30, tzinfo=UTC)
        with factory() as session:
            session.add(_row("gone", "cancelled", "deleted-page", start))
            session.add(_row("live", "planned", "live-page", start + timedelta(minutes=1)))
            session.commit()
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request.url.path)
            if request.url.path.endswith("deleted-page"):
                return httpx.Response(404, json={"message": "Could not find page"})
            return httpx.Response(200, json={"id": "live-page"})

        sync = TrainingNotionSync(factory, client=httpx.Client(transport=httpx.MockTransport(handler)))
        with patch("app.domain.training.notion_sync.settings") as settings:
            settings.notion_token = "token"
            settings.notion_training_data_source_id = "source"
            settings.timezone = "Asia/Tokyo"
            synced = sync.sync_due()
        self.assertEqual(synced, 2)
        self.assertIn("/v1/pages/live-page", calls)
        with factory() as session:
            self.assertIsNotNone(session.get(TrainingSession, "gone").notion_synced_at)


    def test_updated_session_whose_page_was_deleted_is_unlinked(self) -> None:
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        start = datetime(2026, 9, 14, 0, tzinfo=UTC)
        with factory() as session:
            session.add(_row("old", "skipped", "deleted-page", start))
            session.add(_row("new", "planned", "live-page", start + timedelta(days=30)))
            session.commit()

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("deleted-page"):
                return httpx.Response(404, json={"message": "Could not find page"})
            return httpx.Response(200, json={"id": "live-page", "results": []})

        sync = TrainingNotionSync(factory, client=httpx.Client(transport=httpx.MockTransport(handler)))
        with patch("app.domain.training.notion_sync.settings") as settings:
            settings.notion_token = "token"
            settings.notion_training_data_source_id = "source"
            settings.timezone = "Asia/Tokyo"
            self.assertEqual(sync.sync_due(), 2)
        with factory() as session:
            old = session.get(TrainingSession, "old")
            self.assertIsNone(old.notion_page_id)
            self.assertIsNotNone(old.notion_synced_at)

    def _sync_with(self, rows, deleted_response):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        with factory() as session:
            session.add_all(rows)
            session.commit()

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("deleted-page"):
                return deleted_response
            return httpx.Response(200, json={"id": "live-page", "results": []})

        sync = TrainingNotionSync(factory, client=httpx.Client(transport=httpx.MockTransport(handler)))
        return factory, sync.sync_due

    def test_updated_session_whose_page_is_in_trash_is_unlinked(self) -> None:
        start = datetime(2026, 10, 22, 0, tzinfo=UTC)
        factory, sync_due = self._sync_with(
            [_row("trashed", "planned", "deleted-page", start), _row("next", "planned", "live-page", start + timedelta(days=1))],
            httpx.Response(400, json=TRASHED),
        )
        with patch("app.domain.training.notion_sync.settings") as settings:
            settings.notion_token = "token"
            settings.notion_training_data_source_id = "source"
            settings.timezone = "Asia/Tokyo"
            self.assertEqual(sync_due(), 2)
        with factory() as session:
            trashed = session.get(TrainingSession, "trashed")
            self.assertIsNone(trashed.notion_page_id)
            self.assertIsNotNone(trashed.notion_synced_at)
            self.assertIsNotNone(session.get(TrainingSession, "next").notion_synced_at)

    def test_cancelled_session_whose_page_is_in_trash_does_not_block_the_batch(self) -> None:
        start = datetime(2026, 10, 22, 0, tzinfo=UTC)
        factory, sync_due = self._sync_with(
            [_row("gone", "cancelled", "deleted-page", start), _row("live", "planned", "live-page", start + timedelta(minutes=1))],
            httpx.Response(400, json=TRASHED),
        )
        with patch("app.domain.training.notion_sync.settings") as settings:
            settings.notion_token = "token"
            settings.notion_training_data_source_id = "source"
            settings.timezone = "Asia/Tokyo"
            self.assertEqual(sync_due(), 2)

    def test_other_bad_request_still_stops_the_batch(self) -> None:
        start = datetime(2026, 10, 22, 0, tzinfo=UTC)
        _, sync_due = self._sync_with(
            [_row("bad", "planned", "deleted-page", start)],
            httpx.Response(400, json={"code": "validation_error", "message": "Status is not a property that exists."}),
        )
        with patch("app.domain.training.notion_sync.settings") as settings:
            settings.notion_token = "token"
            settings.notion_training_data_source_id = "source"
            settings.timezone = "Asia/Tokyo"
            with self.assertRaises(httpx.HTTPStatusError):
                sync_due()


if __name__ == "__main__":
    unittest.main()
