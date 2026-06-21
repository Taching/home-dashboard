import unittest

from app.domain.voice_commands import VOICE_COMMANDS, VoiceCommand, VoiceCommandInterpreter


class VoiceCommandTests(unittest.TestCase):
    def test_registry_contains_only_executable_actions(self):
        self.assertEqual({item["id"] for item in VOICE_COMMANDS}, {
            "spotify.play_artist", "spotify.pause", "system.volume_up", "system.volume_down",
            "system.volume_set", "light.turn_on", "light.turn_off",
        })

    def test_artist_requires_a_name(self):
        self.assertEqual(
            VoiceCommandInterpreter._validate({"action": "spotify.play_artist", "artist": "Yuuri", "volume_percent": None}),
            VoiceCommand("spotify.play_artist", artist="Yuuri"),
        )
        self.assertEqual(
            VoiceCommandInterpreter._validate({"action": "spotify.play_artist", "artist": None, "volume_percent": None}),
            VoiceCommand("no_match"),
        )

    def test_volume_is_validated(self):
        self.assertEqual(
            VoiceCommandInterpreter._validate({"action": "system.volume_set", "artist": None, "volume_percent": 50}),
            VoiceCommand("system.volume_set", volume_percent=50),
        )
        self.assertEqual(
            VoiceCommandInterpreter._validate({"action": "system.volume_set", "artist": None, "volume_percent": 101}),
            VoiceCommand("no_match"),
        )

    def test_unknown_model_action_fails_closed(self):
        self.assertEqual(
            VoiceCommandInterpreter._validate({"action": "shell.execute", "artist": None, "volume_percent": None}),
            VoiceCommand("no_match"),
        )


if __name__ == "__main__":
    unittest.main()
