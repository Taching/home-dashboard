import json
import unittest

from app.api.router import _model_json, _openclaw_conversation
from app.domain.openclaw import OpenClawMessage


class FakeOpenClaw:
    def __init__(self, configured=True, messages=None, error=None):
        self.is_configured = configured
        self.messages = messages or []
        self.error = error

    def configured(self):
        return self.is_configured

    def history(self):
        if self.error:
            raise self.error
        return self.messages


class OpenClawApiTests(unittest.TestCase):
    def test_conversation_response_serializes_for_stream(self):
        response = _openclaw_conversation(FakeOpenClaw(messages=[
            OpenClawMessage(id="one", role="assistant", text="Hello from Telegram", created_at=None),
        ]))

        payload = json.loads(_model_json(response))

        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["messages"][0]["text"], "Hello from Telegram")

    def test_conversation_reports_unavailable_when_history_fails(self):
        response = _openclaw_conversation(FakeOpenClaw(error=RuntimeError("offline")))

        self.assertEqual(response.status, "unavailable")
        self.assertEqual(response.message, "OpenClaw is unavailable.")


if __name__ == "__main__":
    unittest.main()
