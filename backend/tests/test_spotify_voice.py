import unittest
from unittest.mock import Mock, patch

from app.domain.spotify import SpotifyService


class SpotifyVoiceTests(unittest.TestCase):
    @patch("app.domain.spotify.httpx.put")
    def test_pause_targets_registered_device(self, put):
        response = Mock()
        put.return_value = response
        service = SpotifyService()
        service._access_token = Mock(return_value="token")  # type: ignore[method-assign]
        service._registered_device = Mock(return_value="device-id")  # type: ignore[method-assign]

        service.pause()

        put.assert_called_once_with(
            "https://api.spotify.com/v1/me/player/pause",
            params={"device_id": "device-id"},
            headers={"Authorization": "Bearer token"},
            timeout=15,
        )
        response.raise_for_status.assert_called_once_with()

    @patch("app.domain.spotify.httpx.put")
    @patch("app.domain.spotify.httpx.get")
    def test_change_volume_uses_registered_device_when_not_active(self, get, put):
        devices_response = Mock()
        devices_response.json.return_value = {
            "devices": [{"id": "device-id", "volume_percent": 40, "is_active": False}],
        }
        get.return_value = devices_response
        put_response = Mock()
        put.return_value = put_response
        service = SpotifyService()
        service._access_token = Mock(return_value="token")  # type: ignore[method-assign]
        service._registered_device = Mock(return_value="device-id")  # type: ignore[method-assign]

        self.assertEqual(service.change_volume("down"), 30)

        get.assert_called_once_with(
            "https://api.spotify.com/v1/me/player/devices",
            headers={"Authorization": "Bearer token"},
            timeout=15,
        )
        put.assert_called_once_with(
            "https://api.spotify.com/v1/me/player/volume",
            params={"device_id": "device-id", "volume_percent": 30},
            headers={"Authorization": "Bearer token"},
            timeout=15,
        )


if __name__ == "__main__":
    unittest.main()
