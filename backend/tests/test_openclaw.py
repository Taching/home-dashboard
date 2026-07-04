import unittest

from app.domain.openclaw import OpenClawError, OpenClawService


class FakeOpenClawService(OpenClawService):
    def __init__(self, responses, context_provider=None):
        super().__init__(context_provider)
        self.responses = iter(responses)
        self.requests = []

    def _request(self, method, params):
        self.requests.append((method, params))
        return next(self.responses)

    def _session_key(self):
        return "agent:main:main"


class OpenClawServiceTests(unittest.TestCase):
    def test_history_normalises_gateway_content(self):
        service = FakeOpenClawService([{
            "messages": [
                {"id": "one", "role": "user", "content": [{"text": "Hello"}]},
                {"id": "two", "role": "assistant", "content": [{"type": "text", "text": "Visible reply"}]},
            ]
        }])

        messages = service.history()

        self.assertEqual([(message.role, message.text) for message in messages], [
            ("user", "Hello"), ("assistant", "Visible reply"),
        ])

    def test_history_shows_telegram_message_tool_and_hides_tool_results(self):
        service = FakeOpenClawService([{
            "messages": [
                {"id": "one", "role": "toolResult", "content": [{"type": "toolResult", "text": "internal output"}]},
                {"id": "two", "role": "assistant", "content": [{
                    "type": "toolCall",
                    "name": "message",
                    "arguments": {"message": "Done. I marked the tasks as Done."},
                }]},
            ]
        }])

        messages = service.history()

        self.assertEqual([(message.role, message.text) for message in messages], [
            ("assistant", "Done. I marked the tasks as Done."),
        ])

    def test_send_requires_telegram_delivery_confirmation(self):
        service = FakeOpenClawService([{"result": {"deliveryStatus": "sent", "reply": "Done"}}])

        result = service.send("Turn on the light")

        self.assertEqual(result, {"delivery_status": "sent", "reply": "Done"})

    def test_send_includes_dashboard_context_when_available(self):
        service = FakeOpenClawService(
            [{"result": {"deliveryStatus": "sent"}}],
            context_provider=lambda: "Dashboard data snapshot:\n- Temperature: 22.1 C.",
        )

        service.send("What's happening at home?")

        _, params = service.requests[0]
        self.assertIn("private dashboard context", params["message"])
        self.assertIn("Temperature: 22.1 C.", params["message"])
        self.assertIn("User request: What's happening at home?", params["message"])

    def test_send_continues_without_context_when_provider_fails(self):
        def broken_context():
            raise RuntimeError("calendar unavailable")

        service = FakeOpenClawService(
            [{"result": {"deliveryStatus": "sent"}}],
            context_provider=broken_context,
        )

        service.send("Hello")

        _, params = service.requests[0]
        self.assertEqual(params["message"], "Hello")

    def test_send_accepts_started_gateway_status(self):
        service = FakeOpenClawService([{"status": "started", "runId": "run-one"}])

        result = service.send("Hello")

        self.assertEqual(result, {"delivery_status": "started", "reply": None})

    def test_send_fails_without_delivery_confirmation(self):
        service = FakeOpenClawService([{"result": {"deliveryStatus": "failed"}}])

        with self.assertRaises(OpenClawError):
            service.send("Hello")

    def test_prefers_latest_telegram_session(self):
        session_key = OpenClawService._find_preferred_session_key({
            "sessions": [
                {"key": "agent:main:main", "lastChannel": "webchat", "updatedAt": 20},
                {"key": "agent:main:telegram:direct:older", "lastChannel": "telegram", "updatedAt": 10},
                {"key": "agent:main:telegram:direct:newer", "origin": {"provider": "telegram"}, "updatedAt": 30},
            ]
        })

        self.assertEqual(session_key, "agent:main:telegram:direct:newer")
