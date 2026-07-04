from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SystemStatusSnapshot:
    cpu_temperature_c: float | None
    load_1m: float | None
    load_percent: float | None
    memory_used_percent: float | None
    memory_used_mb: int | None
    memory_total_mb: int | None
    storage_used_percent: float | None
    storage_free_gb: float | None
    storage_total_gb: float | None


class SystemStatusService:
    def __init__(
        self,
        *,
        thermal_path: str | Path = "/sys/class/thermal/thermal_zone0/temp",
        meminfo_path: str | Path = "/proc/meminfo",
        storage_path: str | Path = "/",
    ) -> None:
        self._thermal_path = Path(thermal_path)
        self._meminfo_path = Path(meminfo_path)
        self._storage_path = Path(storage_path)

    def snapshot(self) -> SystemStatusSnapshot:
        memory = self._memory()
        storage = self._storage()
        load_1m, load_percent = self._load()
        return SystemStatusSnapshot(
            cpu_temperature_c=self._cpu_temperature(),
            load_1m=load_1m,
            load_percent=load_percent,
            memory_used_percent=memory["used_percent"],
            memory_used_mb=memory["used_mb"],
            memory_total_mb=memory["total_mb"],
            storage_used_percent=storage["used_percent"],
            storage_free_gb=storage["free_gb"],
            storage_total_gb=storage["total_gb"],
        )

    def _cpu_temperature(self) -> float | None:
        try:
            value = int(self._thermal_path.read_text().strip())
        except (OSError, ValueError):
            return None
        return round(value / 1000, 1)

    def _load(self) -> tuple[float | None, float | None]:
        try:
            load_1m = os.getloadavg()[0]
        except OSError:
            return None, None
        cores = os.cpu_count() or 1
        return round(load_1m, 2), round((load_1m / cores) * 100, 0)

    def _memory(self) -> dict[str, float | int | None]:
        try:
            meminfo = self._parse_meminfo(self._meminfo_path.read_text())
        except OSError:
            return {"used_percent": None, "used_mb": None, "total_mb": None}

        total_kb = meminfo.get("MemTotal")
        available_kb = meminfo.get("MemAvailable")
        if not total_kb or available_kb is None:
            return {"used_percent": None, "used_mb": None, "total_mb": None}

        used_kb = max(total_kb - available_kb, 0)
        return {
            "used_percent": round((used_kb / total_kb) * 100, 0),
            "used_mb": round(used_kb / 1024),
            "total_mb": round(total_kb / 1024),
        }

    def _storage(self) -> dict[str, float | None]:
        try:
            usage = shutil.disk_usage(self._storage_path)
        except OSError:
            return {"used_percent": None, "free_gb": None, "total_gb": None}
        return {
            "used_percent": round((usage.used / usage.total) * 100, 0) if usage.total else None,
            "free_gb": round(usage.free / 1024**3, 1),
            "total_gb": round(usage.total / 1024**3, 1),
        }

    @staticmethod
    def _parse_meminfo(value: str) -> dict[str, int]:
        result: dict[str, int] = {}
        for line in value.splitlines():
            name, _, raw = line.partition(":")
            parts = raw.strip().split()
            if not name or not parts:
                continue
            try:
                result[name] = int(parts[0])
            except ValueError:
                continue
        return result
