from __future__ import annotations

import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WATCHDOG = ROOT / "deploy" / "health-watchdog.sh"


class HealthWatchdogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        self.bin = self.root / "bin"
        self.state = self.root / "state"
        self.project = self.root / "project"
        self.log = self.root / "actions.log"
        self.bin.mkdir()
        self.project.mkdir()
        (self.project / ".env").write_text(
            "WALKINGPAD_BLE_NAME=KS-TEST\nWALKINGPAD_BRIDGE_TOKEN=test\n"
        )
        for name in ("compose.yaml", "compose.pi.yaml", "compose.apple-calendar-bridge.yaml"):
            (self.project / name).touch()

        self._command("curl", 'exit "${FAKE_CURL_EXIT:-0}"')
        self._command(
            "docker",
            """
if [[ "$*" == *" ps --status running --services"* ]]; then
  printf '%s\\n' ${FAKE_RUNNING_SERVICES:-backend frontend calendar-bridge walkingpad-collector}
  exit 0
fi
printf 'docker %s\\n' "$*" >> "$FAKE_ACTION_LOG"
exit "${FAKE_DOCKER_EXIT:-0}"
""",
        )
        self._command(
            "systemctl",
            """
if [[ "$1" == "is-active" && "$3" == "graphical.target" ]]; then
  exit "${FAKE_GRAPHICAL_EXIT:-0}"
fi
if [[ "$1" == "is-active" && "$3" == "chili-kiosk.service" ]]; then
  exit "${FAKE_KIOSK_EXIT:-0}"
fi
printf 'systemctl %s\\n' "$*" >> "$FAKE_ACTION_LOG"
exit "${FAKE_SYSTEMCTL_EXIT:-0}"
""",
        )
        self._command("sleep", "exit 0")

    def _command(self, name: str, body: str) -> None:
        path = self.bin / name
        path.write_text(f"#!/usr/bin/env bash\n{body}\n")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    def run_watchdog(self, **overrides: str) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment.update(
            {
                "PATH": f"{self.bin}:{environment['PATH']}",
                "CHILI_PROJECT_DIR": str(self.project),
                "CHILI_WATCHDOG_STATE_DIR": str(self.state),
                "CHILI_WATCHDOG_FAILURE_THRESHOLD": "2",
                "CHILI_WATCHDOG_COOLDOWN_SECONDS": "900",
                "CHILI_WATCHDOG_RECOVERY_WAIT_SECONDS": "0",
                "FAKE_ACTION_LOG": str(self.log),
            }
        )
        environment.update(overrides)
        return subprocess.run(
            ["bash", str(WATCHDOG)],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )

    def actions(self) -> str:
        return self.log.read_text() if self.log.exists() else ""

    def test_healthy_services_take_no_action(self) -> None:
        result = self.run_watchdog()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.actions(), "")

    def test_dashboard_restarts_only_after_second_failure(self) -> None:
        first = self.run_watchdog(FAKE_CURL_EXIT="1")
        self.assertEqual(first.returncode, 0)
        self.assertEqual(self.actions(), "")

        second = self.run_watchdog(FAKE_CURL_EXIT="1")
        self.assertEqual(second.returncode, 1)
        self.assertIn("restart --no-deps backend frontend", self.actions())
        self.assertIn("still unavailable", second.stdout)

        third = self.run_watchdog(FAKE_CURL_EXIT="1")
        self.assertEqual(third.returncode, 0)
        self.assertEqual(self.actions().count("restart --no-deps backend frontend"), 1)
        self.assertIn("recovery suppressed", third.stdout)

    def test_missing_kiosk_is_restarted_after_second_failure(self) -> None:
        self.run_watchdog(FAKE_KIOSK_EXIT="1")
        self.assertEqual(self.actions(), "")

        result = self.run_watchdog(FAKE_KIOSK_EXIT="1")
        self.assertEqual(result.returncode, 0)
        self.assertIn("systemctl restart chili-kiosk.service", self.actions())


if __name__ == "__main__":
    unittest.main()
