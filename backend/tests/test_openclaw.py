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

    def test_history_dedupes_repeated_assistant_replies(self):
        reply = "Done. I marked the task as Done in Notion."
        service = FakeOpenClawService([{
            "messages": [
                {"id": "text", "role": "assistant", "content": [{"type": "text", "text": reply}]},
                {"id": "tool", "role": "assistant", "content": [{
                    "type": "toolCall",
                    "name": "message",
                    "arguments": {"message": reply},
                }]},
            ]
        }])

        messages = service.history()

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].text, reply)

    def test_history_strips_dashboard_context_from_user_messages(self):
        service = FakeOpenClawService([{
            "messages": [{
                "id": "user",
                "role": "user",
                "content": (
                    "Use this private dashboard context to answer the user's request.\n\n"
                    "Temperature: 22 C\n\n"
                    "User request: Mark the switchbot task done"
                ),
            }],
        }])

        messages = service.history()

        self.assertEqual(messages[0].text, "Mark the switchbot task done")

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

    def test_notify_user_uses_channel_send(self):
        service = FakeOpenClawService(
            [{"result": {"deliveryStatus": "sent", "messageId": "1"}}],
        )
        service._session_key = lambda: "agent:main:telegram:direct:8188515149"  # type: ignore[method-assign]

        result = service.notify_user("Today: https://example.test/daily/2026-09-13")

        self.assertEqual(result["delivery_status"], "sent")
        method, params = service.requests[0]
        self.assertEqual(method, "send")
        self.assertEqual(params["channel"], "telegram")
        self.assertEqual(params["target"], "8188515149")
        self.assertIn("/daily/2026-09-13", params["message"])

    def test_notify_user_fails_without_channel_confirmation(self):
        service = FakeOpenClawService([{"result": {"deliveryStatus": "queued"}}])
        service._session_key = lambda: "agent:main:telegram:direct:8188515149"  # type: ignore[method-assign]

        with self.assertRaises(OpenClawError):
            service.notify_user("Hello")

    def test_target_from_telegram_session_key(self):
        self.assertEqual(
            OpenClawService._target_from_session_key("agent:main:telegram:direct:8188515149"),
            "8188515149",
        )

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
