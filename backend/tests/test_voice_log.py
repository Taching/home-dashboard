import unittest
from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.session import Base
from app.domain.voice_commands import VoiceCommand
from app.domain.voice_log import VoiceLogService


class VoiceLogServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        self.service = VoiceLogService(sessionmaker(bind=engine, expire_on_commit=False))

    def test_record_successful_command(self):
        entry = self.service.record(
            transcript="play Spotify Yuuri",
            command=VoiceCommand("spotify.play_artist", artist="Yuuri"),
            interpret_source="fast_path",
            status="success",
            response_message="Playing Yuuri.",
            audio_seconds=2.4,
            wake_score=0.82,
        )

        self.assertEqual(entry.transcript, "play Spotify Yuuri")
        self.assertEqual(entry.action, "spotify.play_artist")
        self.assertEqual(entry.interpret_source, "fast_path")
        self.assertEqual(entry.status, "success")

        recent = self.service.recent(limit=10)
        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0].artist, "Yuuri")

    def test_record_no_match(self):
        self.service.record(
            transcript="what's the weather",
            command=VoiceCommand("no_match"),
            interpret_source="gpt",
            status="no_match",
            response_message="I don't know that command yet.",
        )

        recent = self.service.recent(limit=10)
        self.assertEqual(recent[0].status, "no_match")
        self.assertEqual(recent[0].action, "no_match")


if __name__ == "__main__":
    unittest.main()
