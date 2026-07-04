import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.router import api_router
from app.domain.voice_commands import VoiceCommand, VoiceInterpretation
from app.domain.activity_feed import ActivityFeedService
from app.domain.voice_log import VoiceLogService
from app.domain.voice_state import VoiceStateService


class FakeInterpreter:
    def interpret(self, transcript: str) -> VoiceInterpretation:
        return VoiceInterpretation(
            VoiceCommand("openclaw.send_message", message="What's next today?"),
            "gpt",
        )


class FakeOpenClaw:
    def __init__(self) -> None:
        self.sent: list[str] = []

    def send(self, message: str) -> dict[str, str | None]:
        self.sent.append(message)
        return {"delivery_status": "started", "reply": None}


class VoiceOpenClawApiTests(unittest.TestCase):
    def test_voice_transcript_sends_message_to_openclaw(self):
        app = FastAPI()
        app.include_router(api_router, prefix="/api/v1")
        app.state.voice_command_interpreter = FakeInterpreter()
        app.state.voice_state_service = VoiceStateService()
        app.state.activity_feed_service = ActivityFeedService()
        app.state.voice_log_service = VoiceLogService()
        app.state.openclaw_service = FakeOpenClaw()

        response = TestClient(app).post(
            "/api/v1/voice/transcripts",
            json={"text": "ask Chili what's next today"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "success", "message": "Sent to Chili."})
        self.assertEqual(app.state.openclaw_service.sent, ["What's next today?"])


if __name__ == "__main__":
    unittest.main()
