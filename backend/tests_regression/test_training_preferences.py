import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.router import api_router
from app.database.session import Base
from app.domain.training_preferences import TrainingPreferencesService


def factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


class TrainingPreferencesServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = TrainingPreferencesService(factory())

    def test_get_before_any_save_returns_nulls(self) -> None:
        self.assertEqual(self.service.get(), {"notes": None, "updated_at": None})

    def test_save_creates_the_singleton_row(self) -> None:
        result = self.service.save("Bad left knee. Prefers running outdoors over the treadmill.")
        self.assertEqual(result["notes"], "Bad left knee. Prefers running outdoors over the treadmill.")
        self.assertIsNotNone(result["updated_at"])
        self.assertEqual(self.service.get()["notes"], result["notes"])

    def test_save_overwrites_the_existing_row_rather_than_duplicating(self) -> None:
        self.service.save("First note.")
        second = self.service.save("Second note.")
        self.assertEqual(second["notes"], "Second note.")
        self.assertEqual(self.service.get()["notes"], "Second note.")

    def test_save_blank_or_whitespace_clears_notes_to_none(self) -> None:
        self.service.save("Something.")
        cleared = self.service.save("   ")
        self.assertIsNone(cleared["notes"])

    def test_save_trims_and_caps_length(self) -> None:
        result = self.service.save("  padded with spaces  ")
        self.assertEqual(result["notes"], "padded with spaces")
        long_result = self.service.save("x" * 5000)
        self.assertEqual(len(long_result["notes"]), 2000)

    def test_prompt_snippet_is_empty_when_no_notes(self) -> None:
        self.assertEqual(self.service.prompt_snippet(), "")

    def test_prompt_snippet_wraps_notes_for_prompt_injection(self) -> None:
        self.service.save("Avoid burpees, sensitive right shoulder.")
        snippet = self.service.prompt_snippet()
        self.assertIn("Avoid burpees, sensitive right shoulder.", snippet)
        self.assertIn("never a scheduling rule", snippet)


class TrainingPreferencesApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = FastAPI()
        self.app.include_router(api_router, prefix="/api/v1")
        self.app.state.training_preferences_service = TrainingPreferencesService(factory())
        self.client = TestClient(self.app)

    def test_get_when_unset_returns_nulls(self) -> None:
        response = self.client.get("/api/v1/training/preferences")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"notes": None, "updated_at": None})

    def test_put_then_get_round_trips(self) -> None:
        put_response = self.client.put("/api/v1/training/preferences", json={"notes": "Prefers morning BJJ."})
        self.assertEqual(put_response.status_code, 200, put_response.text)
        self.assertEqual(put_response.json()["notes"], "Prefers morning BJJ.")

        get_response = self.client.get("/api/v1/training/preferences")
        self.assertEqual(get_response.json()["notes"], "Prefers morning BJJ.")

    def test_put_with_null_notes_clears_it(self) -> None:
        self.client.put("/api/v1/training/preferences", json={"notes": "Something."})
        response = self.client.put("/api/v1/training/preferences", json={"notes": None})
        self.assertIsNone(response.json()["notes"])


if __name__ == "__main__":
    unittest.main()
