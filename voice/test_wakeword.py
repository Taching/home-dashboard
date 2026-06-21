import unittest

from voice.wakeword import WakeWordGate


class WakeWordGateTests(unittest.TestCase):
    def test_sustained_high_score_only_triggers_once(self):
        gate = WakeWordGate(threshold=0.5, rearm_seconds=1.0, cooldown_seconds=3.0)

        self.assertTrue(gate.observe(0.9, 0.0))
        self.assertFalse(gate.observe(0.9, 3.5))
        self.assertFalse(gate.observe(0.9, 10.0))

    def test_low_score_interval_rearms_for_next_utterance(self):
        gate = WakeWordGate(threshold=0.5, rearm_seconds=1.0, cooldown_seconds=3.0)

        self.assertTrue(gate.observe(0.9, 0.0))
        self.assertFalse(gate.observe(0.1, 0.1))
        self.assertFalse(gate.observe(0.1, 1.0))
        self.assertFalse(gate.observe(0.1, 1.1))
        self.assertTrue(gate.observe(0.9, 3.1))


if __name__ == "__main__":
    unittest.main()
