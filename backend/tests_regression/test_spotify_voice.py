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

    @patch("app.domain.spotify.httpx.put")
    def test_start_dj_enables_shuffle_and_plays_dj_context(self, put):
        shuffle_response = Mock()
        play_response = Mock()
        play_response.status_code = 204
        put.side_effect = [shuffle_response, play_response]
        service = SpotifyService()
        service._access_token = Mock(return_value="token")  # type: ignore[method-assign]
        service._registered_device = Mock(return_value="device-id")  # type: ignore[method-assign]

        service.start_dj()

        put.assert_any_call(
            "https://api.spotify.com/v1/me/player/shuffle",
            params={"device_id": "device-id", "state": "true"},
            headers={"Authorization": "Bearer token"},
            timeout=15,
        )
        put.assert_any_call(
            "https://api.spotify.com/v1/me/player/play",
            params={"device_id": "device-id"},
            headers={"Authorization": "Bearer token"},
            json={"context_uri": "spotify:playlist:37i9dQZF1EYkqdzj48dyYq"},
            timeout=15,
        )

    @patch("app.domain.spotify.httpx.put")
    @patch("app.domain.spotify.httpx.get")
    def test_start_dj_falls_back_to_recent_mix(self, get, put):
        shuffle_response = Mock()
        dj_response = Mock()
        dj_response.status_code = 404
        recent_response = Mock()
        recent_response.json.return_value = {
            "items": [{"track": {"uri": "spotify:track:abc"}}, {"track": {"uri": "spotify:track:def"}}],
        }
        mix_response = Mock()
        put.side_effect = [shuffle_response, dj_response, mix_response]
        get.return_value = recent_response
        service = SpotifyService()
        service._access_token = Mock(return_value="token")  # type: ignore[method-assign]
        service._registered_device = Mock(return_value="device-id")  # type: ignore[method-assign]

        service.start_dj()

        get.assert_called_once()
        put.assert_any_call(
            "https://api.spotify.com/v1/me/player/play",
            params={"device_id": "device-id"},
            headers={"Authorization": "Bearer token"},
            json={"uris": ["spotify:track:abc", "spotify:track:def"]},
            timeout=15,
        )


if __name__ == "__main__":
    unittest.main()
