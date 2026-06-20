import unittest

from app.domain.voice_commands import VoiceCommand, parse_voice_command


class VoiceCommandTests(unittest.TestCase):
    def test_play_artist(self):
        self.assertEqual(parse_voice_command("Play Spotify Yuuri"), VoiceCommand("spotify.play_artist", "yuuri"))

    def test_volume_up_variants(self):
        self.assertEqual(parse_voice_command("turn it up"), VoiceCommand("spotify.volume_up"))

    def test_volume_down_variants(self):
        self.assertEqual(parse_voice_command("make it quieter"), VoiceCommand("spotify.volume_down"))

    def test_unknown_command(self):
        self.assertIsNone(parse_voice_command("tell me a joke"))


if __name__ == "__main__":
    unittest.main()
