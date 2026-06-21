import unittest

from app.domain.voice_state import VoiceStateService


class VoiceStateTests(unittest.TestCase):
    def test_error_includes_message(self):
        service = VoiceStateService()

        service.set_state("error", message="Spotify is not connected")

        snapshot = service.current()
        self.assertEqual(snapshot.state, "error")
        self.assertEqual(snapshot.message, "Spotify is not connected")

    def test_idle_clears_message_and_transcript(self):
        service = VoiceStateService()
        service.set_state("error", transcript="play music", message="Try again")

        service.set_state("idle")

        snapshot = service.current()
        self.assertEqual(snapshot.state, "idle")
        self.assertIsNone(snapshot.transcript)
        self.assertIsNone(snapshot.message)


if __name__ == "__main__":
    unittest.main()
