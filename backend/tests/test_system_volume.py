import unittest
from unittest.mock import Mock

from app.domain.system_volume import PiVolumeService


class PiVolumeTests(unittest.TestCase):
    def test_adjust_down_clamps_and_reads_effective_volume(self):
        service = PiVolumeService(card=0, control="PCM", step=10)
        service._run = Mock(side_effect=[
            Mock(stdout="Front Left: Playback 20 [8%]"),
            Mock(stdout=""),
            Mock(stdout="Front Left: Playback 0 [0%]"),
        ])

        self.assertEqual(service.adjust("down"), 0)
        self.assertEqual(service._run.call_args_list[1].args, ("sset", "PCM", "0%"))

    def test_set_rejects_invalid_percentage(self):
        with self.assertRaises(ValueError):
            PiVolumeService().set(101)


if __name__ == "__main__":
    unittest.main()
