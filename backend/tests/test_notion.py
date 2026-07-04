from datetime import UTC, date, datetime
import unittest
from unittest.mock import patch

import httpx

from app.domain.notion import NotionService


class FakeClient:
    def __init__(self, pages):
        self.pages = pages

    def post(self, *args, **kwargs):
        return httpx.Response(200, json={"results": self.pages}, request=httpx.Request("POST", "https://api.notion.com"))


def page(page_id, title, due, done=False):
    return {
        "id": page_id,
        "properties": {
            "Name": {"type": "title", "title": [{"plain_text": title}]},
            "Due Date": {"type": "date", "date": {"start": due} if due else None},
            "Done": {"type": "checkbox", "checkbox": done},
        },
    }


class NotionServiceTests(unittest.TestCase):
    @patch("app.domain.notion.settings.notion_token", "secret")
    @patch("app.domain.notion.settings.notion_database_id", "database")
    @patch("app.domain.notion.settings.notion_data_source_id", None)
    @patch("app.domain.notion.settings.notion_due_property", "Due Date")
    def test_today_returns_incomplete_today_and_overdue_tasks(self):
        service = NotionService(client=FakeClient([
            page("today", "Buy milk", "2026-07-04"),
            page("overdue", "Pay bill", "2026-07-03"),
            page("future", "Tomorrow", "2026-07-05"),
            page("done", "Done task", "2026-07-04", done=True),
        ]))

        with patch("app.domain.notion.datetime") as fake_datetime:
            fake_datetime.now.side_effect = lambda tz=None: datetime(2026, 7, 4, 12, tzinfo=tz or UTC)
            fake_datetime.fromisoformat.side_effect = datetime.fromisoformat
            fake_datetime.combine.side_effect = datetime.combine
            fake_datetime.max = datetime.max
            status, _, tasks = service.today()

        self.assertEqual(status, "ready")
        self.assertEqual([task.id for task in tasks], ["overdue", "today", "future"])
        self.assertTrue(tasks[0].is_overdue)
        self.assertFalse(tasks[1].is_overdue)
        self.assertFalse(tasks[2].is_overdue)

    @patch("app.domain.notion.settings.notion_token", "secret")
    @patch("app.domain.notion.settings.notion_database_id", "database")
    @patch("app.domain.notion.settings.notion_data_source_id", None)
    def test_default_due_property_matches_dashboard_database(self):
        service = NotionService(client=FakeClient([
            page("today", "Review layout", "2026-07-04"),
        ]))

        with patch("app.domain.notion.datetime") as fake_datetime:
            fake_datetime.now.side_effect = lambda tz=None: datetime(2026, 7, 4, 12, tzinfo=tz or UTC)
            fake_datetime.fromisoformat.side_effect = datetime.fromisoformat
            fake_datetime.combine.side_effect = datetime.combine
            fake_datetime.max = datetime.max
            status, _, tasks = service.today()

        self.assertEqual(status, "ready")
        self.assertEqual([task.title for task in tasks], ["Review layout"])

    @patch("app.domain.notion.settings.notion_token", None)
    @patch("app.domain.notion.settings.notion_database_id", None)
    @patch("app.domain.notion.settings.notion_data_source_id", None)
    def test_not_configured_without_token_or_database(self):
        status, synced_at, tasks = NotionService(client=FakeClient([])).today()

        self.assertEqual(status, "not_configured")
        self.assertIsNone(synced_at)
        self.assertEqual(tasks, [])


if __name__ == "__main__":
    unittest.main()
