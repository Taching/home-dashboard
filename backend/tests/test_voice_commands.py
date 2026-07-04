import unittest

from app.domain.voice_commands import VOICE_COMMANDS, VoiceCommand, VoiceCommandInterpreter, match_voice_command_fast_path


class VoiceCommandTests(unittest.TestCase):
    def test_registry_contains_only_executable_actions(self):
        self.assertEqual({item["id"] for item in VOICE_COMMANDS}, {
            "spotify.play_artist", "spotify.pause", "system.volume_up", "system.volume_down",
            "system.volume_set", "light.turn_on", "light.turn_off", "openclaw.send_message",
        })

    def test_artist_requires_a_name(self):
        self.assertEqual(
            VoiceCommandInterpreter._validate({"action": "spotify.play_artist", "artist": "Yuuri", "volume_percent": None, "message": None}),
            VoiceCommand("spotify.play_artist", artist="Yuuri"),
        )
        self.assertEqual(
            VoiceCommandInterpreter._validate({"action": "spotify.play_artist", "artist": None, "volume_percent": None, "message": None}),
            VoiceCommand("no_match"),
        )

    def test_volume_is_validated(self):
        self.assertEqual(
            VoiceCommandInterpreter._validate({"action": "system.volume_set", "artist": None, "volume_percent": 50, "message": None}),
            VoiceCommand("system.volume_set", volume_percent=50),
        )
        self.assertEqual(
            VoiceCommandInterpreter._validate({"action": "system.volume_set", "artist": None, "volume_percent": 101, "message": None}),
            VoiceCommand("no_match"),
        )

    def test_openclaw_message_requires_content(self):
        self.assertEqual(
            VoiceCommandInterpreter._validate({"action": "openclaw.send_message", "artist": None, "volume_percent": None, "message": "What's on my calendar?"}),
            VoiceCommand("openclaw.send_message", message="What's on my calendar?"),
        )
        self.assertEqual(
            VoiceCommandInterpreter._validate({"action": "openclaw.send_message", "artist": None, "volume_percent": None, "message": "   "}),
            VoiceCommand("no_match"),
        )

    def test_unknown_model_action_fails_closed(self):
        self.assertEqual(
            VoiceCommandInterpreter._validate({"action": "shell.execute", "artist": None, "volume_percent": None, "message": None}),
            VoiceCommand("no_match"),
        )

    def test_fast_path_matches_common_commands(self):
        self.assertEqual(match_voice_command_fast_path("pause"), VoiceCommand("spotify.pause"))
        self.assertEqual(match_voice_command_fast_path("turn on the lights"), VoiceCommand("light.turn_on"))
        self.assertEqual(match_voice_command_fast_path("volume up"), VoiceCommand("system.volume_up"))
        self.assertEqual(
            match_voice_command_fast_path("set volume to 40 percent"),
            VoiceCommand("system.volume_set", volume_percent=40),
        )
        self.assertEqual(
            match_voice_command_fast_path("play Spotify Yuuri"),
            VoiceCommand("spotify.play_artist", artist="Yuuri"),
        )
        self.assertIsNone(match_voice_command_fast_path("ask Chili what's on my calendar"))


if __name__ == "__main__":
    unittest.main()
