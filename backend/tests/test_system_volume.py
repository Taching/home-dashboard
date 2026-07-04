import unittest
from unittest.mock import Mock

from app.domain.system_volume import PiVolumeService


class PiVolumeTests(unittest.TestCase):
    def test_adjust_down_clamps_and_reads_effective_volume(self):
        service = PiVolumeService(card=0, control="PCM", step=10)
        service._run_amixer = Mock(side_effect=[
            Mock(stdout="Front Left: Playback 20 [8%]"),
            Mock(stdout=""),
            Mock(stdout="Front Left: Playback 0 [0%]"),
        ])
        service._prefer_pulse = Mock(return_value=False)  # type: ignore[method-assign]

        self.assertEqual(service.adjust("down"), 0)
        self.assertEqual(service._run_amixer.call_args_list[1].args, ("sset", "PCM", "0%"))

    def test_set_rejects_invalid_percentage(self):
        with self.assertRaises(ValueError):
            PiVolumeService().set(101)

    def test_set_uses_pulse_when_available(self):
        service = PiVolumeService()
        service._prefer_pulse = Mock(return_value=True)  # type: ignore[method-assign]
        service._run_pactl = Mock(side_effect=[
            Mock(stdout=""),
            Mock(stdout="Volume: front-left: 65536 / 100%"),
        ])

        self.assertEqual(service.set(100), 100)
        service._run_pactl.assert_any_call("set-sink-volume", "@DEFAULT_SINK@", "100%")

    def test_output_label_reads_default_sink_description(self):
        service = PiVolumeService()
        service._prefer_pulse = Mock(return_value=True)  # type: ignore[method-assign]
        service._run_pactl = Mock(side_effect=[
            Mock(stdout="bluez_output.test\n"),
            Mock(stdout="Sink #1\nName: bluez_output.test\nDescription: Bose Revolve\n"),
        ])

        self.assertEqual(service.output_label(), "Bose Revolve")


if __name__ == "__main__":
    unittest.main()
