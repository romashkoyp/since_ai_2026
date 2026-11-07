"""Persistence for analysis runs: MongoDB Atlas when MONGODB_URI is set and reachable, else in-process memory.

A run (AnalysisRecord) is written once and never changed, so readers can cache it by run_id.
The dashboard always shows the most recent run.
"""

from __future__ import annotations

import json
import logging
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Protocol

from pymongo import DESCENDING, MongoClient
from pymongo.database import Database
from pymongo.errors import PyMongoError

from .models import AnalysisRecord, AnalysisRunSummary
from .settings import Settings

# Use uvicorn's logger so startup messages show in the terminal.
log = logging.getLogger("uvicorn.error")

RUNS = "analysis_runs"


class RunStore(Protocol):
    backend: str

    def save(self, record: AnalysisRecord) -> None: ...
    def latest(self) -> AnalysisRecord | None: ...
    def get(self, run_id: str) -> AnalysisRecord | None: ...
    def list(self, limit: int = 20) -> list[AnalysisRunSummary]: ...
    def close(self) -> None: ...


class MemoryRunStore:
    backend = "memory"

    def __init__(self) -> None:
        self._runs: dict[str, AnalysisRecord] = {}
        self._lock = threading.Lock()

    def save(self, record: AnalysisRecord) -> None:
        with self._lock:
            self._runs[record.summary.run_id] = record

    def _ordered(self) -> list[AnalysisRecord]:
        with self._lock:
            return sorted(self._runs.values(), key=lambda r: r.summary.created_utc, reverse=True)

    def latest(self) -> AnalysisRecord | None:
        runs = self._ordered()
        return runs[0] if runs else None

    def get(self, run_id: str) -> AnalysisRecord | None:
        with self._lock:
            return self._runs.get(run_id)

    def list(self, limit: int = 20) -> list[AnalysisRunSummary]:
        return [r.summary for r in self._ordered()[:limit]]

    def close(self) -> None:
        pass


class MongoRunStore:
    backend = "mongodb"
    _CACHE_SIZE = 4

    def __init__(self, client: MongoClient, db: Database) -> None:
        self._client = client
        self._runs = db[RUNS]
        self._runs.create_index([("summary.created_utc", DESCENDING)])
        self._cache: OrderedDict[str, AnalysisRecord] = OrderedDict()
        self._lock = threading.Lock()

    def _remember(self, record: AnalysisRecord) -> AnalysisRecord:
        with self._lock:
            self._cache[record.summary.run_id] = record
            self._cache.move_to_end(record.summary.run_id)
            while len(self._cache) > self._CACHE_SIZE:
                self._cache.popitem(last=False)
        return record

    def save(self, record: AnalysisRecord) -> None:
        self._runs.insert_one({"_id": record.summary.run_id, **record.model_dump(mode="json")})
        self._remember(record)

    def get(self, run_id: str) -> AnalysisRecord | None:
        with self._lock:
            if run_id in self._cache:
                return self._cache[run_id]
        doc = self._runs.find_one({"_id": run_id}, {"_id": 0})
        return self._remember(AnalysisRecord.model_validate(doc)) if doc else None

    def latest(self) -> AnalysisRecord | None:
        head = self._runs.find_one({}, {"_id": 1}, sort=[("summary.created_utc", DESCENDING)])
        return self.get(head["_id"]) if head else None

    def list(self, limit: int = 20) -> list[AnalysisRunSummary]:
        cursor = self._runs.find({}, {"_id": 0, "summary": 1}).sort("summary.created_utc", DESCENDING).limit(limit)
        return [AnalysisRunSummary.model_validate(d["summary"]) for d in cursor]

    def close(self) -> None:
        self._client.close()


def open_store(settings: Settings) -> RunStore:
    """Connect to Atlas when configured; fall back to memory so the API always starts."""
    if not settings.mongodb_uri:
        log.warning("MongoDB: not connected — MONGODB_URI missing; runs are kept in memory")
        return MemoryRunStore()
    log.info("MongoDB: connecting to Atlas (database=%s)…", settings.mongodb_db)
    try:
        client = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=8000, appname="since-ai-server")
        client.admin.command("ping")
        store = MongoRunStore(client, client[settings.mongodb_db])
    except PyMongoError as exc:
        log.warning("MongoDB: not connected — %s; runs are kept in memory", exc)
        return MemoryRunStore()
    log.info("MongoDB: connected — database=%s", settings.mongodb_db)
    return store


def ensure_seed(store: RunStore, seed_path: Path) -> None:
    """Load the bundled demo run when the store has no runs yet, so the dashboard shows model output at once."""
    if store.latest() is not None:
        return
    if not seed_path.exists():
        log.warning("Seed run: %s not found; dashboard is empty until data is uploaded", seed_path)
        return
    record = AnalysisRecord.model_validate(json.loads(seed_path.read_text(encoding="utf-8")))
    store.save(record)
    log.info("Seed run: loaded %s (%d pumps, %d alerts)", record.summary.run_id, record.summary.pumps,
             record.summary.alerts)
