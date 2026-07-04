import unittest

SPEECH_RMS_THRESHOLD = 280
SILENCE_END_RMS_THRESHOLD = 180
RMS_SMOOTHING = 0.72


def simulate_recording(rms_values: list[float], *, silence_seconds: float = 1.1, min_seconds: float = 0.8) -> int:
    frame_seconds = 1_280 / 16_000
    min_frames = round(min_seconds / frame_seconds)
    silence_frames_needed = round(silence_seconds / frame_seconds)
    silent_frames = 0
    heard_speech = False
    smoothed_rms = 0.0
    frames = 0

    for rms in rms_values:
        frames += 1
        smoothed_rms = rms if smoothed_rms == 0.0 else RMS_SMOOTHING * smoothed_rms + (1.0 - RMS_SMOOTHING) * rms
        if smoothed_rms >= SPEECH_RMS_THRESHOLD:
            heard_speech = True
            silent_frames = 0
        elif heard_speech and smoothed_rms < SILENCE_END_RMS_THRESHOLD:
            silent_frames += 1
            if frames >= min_frames and silent_frames >= silence_frames_needed:
                break

    return frames


class RecordingEndDetectionTests(unittest.TestCase):
    def test_mid_phrase_dip_does_not_end_early(self):
        loud = [420] * 8
        dip = [240] * 4
        tail = [430] * 20
        frames = simulate_recording(loud + dip + tail)
        self.assertEqual(frames, len(loud + dip + tail))

    def test_sustained_silence_ends_recording(self):
        loud = [420] * 12
        quiet = [120] * 20
        frames = simulate_recording(loud + quiet)
        self.assertLess(frames, len(loud + quiet))


if __name__ == "__main__":
    unittest.main()
