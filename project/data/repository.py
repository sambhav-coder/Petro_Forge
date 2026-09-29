"""Storage abstraction (Priority 1, Part U).

Supports in-memory, JSONL files, and future PostgreSQL/TimescaleDB
(implement the same DataRepository interface). Path handling is strict:
entity filenames are fixed; base directories rejecting absolute paths
and parent traversal.
"""

import csv
import json
import os
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from .schema import CSSCycleRecord, TelemetryRecord, WellRecord

ENTITY_FILES = {
    "telemetry": "telemetry.jsonl",
    "wells": "wells.jsonl",
    "cycles": "cycles.jsonl",
}


def safe_base_dir(base_dir: str) -> str:
    """Reject absolute paths (Windows, POSIX) and parent traversal."""
    if not isinstance(base_dir, str) or base_dir.strip() == "":
        raise ValueError("base_dir must be a non-empty relative path")
    if os.path.isabs(base_dir) or base_dir.startswith(("/", "\\")):
        raise ValueError("base_dir must be relative")
    if os.path.splitdrive(base_dir)[0]:
        raise ValueError("base_dir must be relative")
    norm = os.path.normpath(base_dir)
    if norm == ".." or norm.startswith(".." + os.sep) or ".." in norm.split(os.sep):
        raise ValueError("base_dir must not traverse parents")
    return norm


class DataRepository(ABC):
    @abstractmethod
    def save_telemetry(self, records: List[TelemetryRecord]) -> int: ...
    @abstractmethod
    def get_telemetry(self, well_id: Optional[str] = None) -> List[TelemetryRecord]: ...
    @abstractmethod
    def save_wells(self, records: List[WellRecord]) -> int: ...
    @abstractmethod
    def get_wells(self) -> List[WellRecord]: ...
    @abstractmethod
    def save_cycles(self, records: List[CSSCycleRecord]) -> int: ...
    @abstractmethod
    def get_cycles(self, well_id: Optional[str] = None) -> List[CSSCycleRecord]: ...
    @abstractmethod
    def counts(self) -> Dict[str, int]: ...


class InMemoryRepository(DataRepository):
    def __init__(self) -> None:
        self._telemetry: List[TelemetryRecord] = []
        self._wells: Dict[str, WellRecord] = {}
        self._cycles: List[CSSCycleRecord] = []

    def save_telemetry(self, records: List[TelemetryRecord]) -> int:
        self._telemetry.extend(records)
        return len(records)

    def get_telemetry(self, well_id: Optional[str] = None) -> List[TelemetryRecord]:
        if well_id is None:
            return list(self._telemetry)
        return [r for r in self._telemetry if r.well_id == well_id]

    def save_wells(self, records: List[WellRecord]) -> int:
        for r in records:
            self._wells[r.well_id] = r
        return len(records)

    def get_wells(self) -> List[WellRecord]:
        return list(self._wells.values())

    def save_cycles(self, records: List[CSSCycleRecord]) -> int:
        self._cycles.extend(records)
        return len(records)

    def get_cycles(self, well_id: Optional[str] = None) -> List[CSSCycleRecord]:
        if well_id is None:
            return list(self._cycles)
        return [c for c in self._cycles if c.well_id == well_id]

    def counts(self) -> Dict[str, int]:
        return {
            "telemetry": len(self._telemetry),
            "wells": len(self._wells),
            "cycles": len(self._cycles),
        }


class JsonlFileRepository(InMemoryRepository):
    """File-backed repository: one JSONL file per entity under base_dir."""

    def __init__(self, base_dir: str = "project/data/processed") -> None:
        super().__init__()
        self.base_dir = safe_base_dir(base_dir)
        os.makedirs(self.base_dir, exist_ok=True)
        self._load_all()

    def _path(self, entity: str) -> str:
        return os.path.join(self.base_dir, ENTITY_FILES[entity])

    def _load_all(self) -> None:
        for entity, model in (("telemetry", TelemetryRecord),
                              ("wells", WellRecord), ("cycles", CSSCycleRecord)):
            path = self._path(entity)
            if not os.path.exists(path):
                continue
            with open(path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        obj = model(**json.loads(line))
                        if entity == "wells":
                            self._wells[obj.well_id] = obj
                        elif entity == "telemetry":
                            self._telemetry.append(obj)
                        else:
                            self._cycles.append(obj)

    def _persist(self, entity: str, records: list) -> None:
        with open(self._path(entity), "a", encoding="utf-8") as fh:
            for r in records:
                fh.write(r.model_dump_json() + "\n")

    def save_telemetry(self, records: List[TelemetryRecord]) -> int:
        self._persist("telemetry", records)
        return super().save_telemetry(records)

    def save_wells(self, records: List[WellRecord]) -> int:
        self._persist("wells", records)
        return super().save_wells(records)

    def save_cycles(self, records: List[CSSCycleRecord]) -> int:
        self._persist("cycles", records)
        return super().save_cycles(records)


def load_telemetry_csv(path: str, well_id: str, source_id: str) -> List[dict]:
    """Read a CSV into raw dicts (pandas only for parsing; validation downstream)."""
    import pandas as pd

    frame = pd.read_csv(path)
    records = []
    for _, row in frame.iterrows():
        raw = {k: (None if pd.isna(v) else v) for k, v in row.to_dict().items()}
        raw.setdefault("well_id", well_id)
        raw.setdefault("source_id", source_id)
        records.append(raw)
    return records
