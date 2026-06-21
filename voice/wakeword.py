"""Stateful wake-word gating independent of the model implementation."""

from dataclasses import dataclass, field


@dataclass
class WakeWordGate:
    threshold: float
    rearm_seconds: float
    cooldown_seconds: float
    armed: bool = True
    last_detection_at: float | None = None
    low_score_since: float | None = field(default=None, init=False)

    def observe(self, score: float, now: float) -> bool:
        """Return true once per distinct wake utterance.

        A detector must remain below the threshold for ``rearm_seconds`` after
        a detection before another high score is accepted.
        """
        if not self.armed:
            if score < self.threshold:
                self.low_score_since = self.low_score_since if self.low_score_since is not None else now
                if now - self.low_score_since >= self.rearm_seconds:
                    self.armed = True
                    self.low_score_since = None
            else:
                self.low_score_since = None
            return False

        if score < self.threshold:
            return False
        if self.last_detection_at is not None and now - self.last_detection_at < self.cooldown_seconds:
            return False

        self.armed = False
        self.low_score_since = None
        self.last_detection_at = now
        return True
