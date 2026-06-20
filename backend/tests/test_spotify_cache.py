import unittest
from unittest.mock import Mock, patch

from app.domain.spotify import SpotifyService


class SpotifyNowPlayingCacheTests(unittest.TestCase):
    def test_now_playing_reuses_short_lived_cache(self) -> None:
        service = SpotifyService()
        service.status = Mock(return_value="ready")  # type: ignore[method-assign]
        service._access_token = Mock(return_value="token")  # type: ignore[method-assign]
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "item": {
                "name": "Song",
                "artists": [{"name": "Artist"}],
                "album": {"images": [{"url": "https://example.test/art.jpg"}]},
            },
            "device": {"name": "Chili"},
            "is_playing": True,
        }

        with patch("app.domain.spotify.httpx.get", return_value=response) as get:
            first = service.now_playing()
            second = service.now_playing()

        self.assertEqual(first["track"], "Song")
        self.assertEqual(second["track"], "Song")
        get.assert_called_once()

