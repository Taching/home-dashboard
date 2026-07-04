import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.domain.system_status import SystemStatusService


class SystemStatusServiceTests(unittest.TestCase):
    def test_snapshot_reads_pi_health_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            thermal = root / "temp"
            meminfo = root / "meminfo"
            thermal.write_text("55125")
            meminfo.write_text(
                "\n".join([
                    "MemTotal:        2048000 kB",
                    "MemAvailable:   1024000 kB",
                ])
            )

            service = SystemStatusService(
                thermal_path=thermal,
                meminfo_path=meminfo,
                storage_path=root,
            )

            with patch("app.domain.system_status.os.getloadavg", return_value=(2.0, 1.0, 0.5)), \
                 patch("app.domain.system_status.os.cpu_count", return_value=4):
                snapshot = service.snapshot()

        self.assertEqual(snapshot.cpu_temperature_c, 55.1)
        self.assertEqual(snapshot.load_1m, 2.0)
        self.assertEqual(snapshot.load_percent, 50)
        self.assertEqual(snapshot.memory_used_percent, 50)
        self.assertEqual(snapshot.memory_used_mb, 1000)
        self.assertEqual(snapshot.memory_total_mb, 2000)
        self.assertIsNotNone(snapshot.storage_used_percent)
        self.assertIsNotNone(snapshot.storage_free_gb)
        self.assertIsNotNone(snapshot.storage_total_gb)


if __name__ == "__main__":
    unittest.main()
