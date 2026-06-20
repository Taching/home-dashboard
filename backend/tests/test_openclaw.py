import unittest

from app.domain.openclaw import OpenClawError, OpenClawService


class FakeOpenClawService(OpenClawService):
    def __init__(self, responses):
        super().__init__()
        self.responses = iter(responses)

    def _request(self, method, params):
        return next(self.responses)


class OpenClawServiceTests(unittest.TestCase):
    def test_history_normalises_gateway_content(self):
        service = FakeOpenClawService([{
            "messages": [
                {"id": "one", "role": "user", "content": [{"text": "Hello"}]},
                {"id": "two", "role": "toolResult", "content": "Visible reply"},
            ]
        }])

        messages = service.history()

        self.assertEqual([(message.role, message.text) for message in messages], [
            ("user", "Hello"), ("assistant", "Visible reply"),
        ])

    def test_send_requires_telegram_delivery_confirmation(self):
        service = FakeOpenClawService([{"result": {"deliveryStatus": "sent", "reply": "Done"}}])

        result = service.send("Turn on the light")

        self.assertEqual(result, {"delivery_status": "sent", "reply": "Done"})

    def test_send_fails_without_delivery_confirmation(self):
        service = FakeOpenClawService([{"result": {"deliveryStatus": "failed"}}])

        with self.assertRaises(OpenClawError):
            service.send("Hello")
