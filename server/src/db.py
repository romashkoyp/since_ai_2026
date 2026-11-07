"""MongoDB Atlas access. Falls back to in-memory sample data when MONGODB_URI is unset or unreachable."""

from __future__ import annotations

import csv
import logging
import os
from pathlib import Path

from pymongo import ASCENDING, MongoClient
from pymongo.database import Database
from pymongo.errors import PyMongoError

from .models import AlertPrediction, AssetStatus
from .sample_data import SAMPLE_ALERTS, SAMPLE_ASSETS

# Use uvicorn's logger so startup messages show in the terminal.
log = logging.getLogger("uvicorn.error")

SEED_ALERTS_CSV = Path(__file__).resolve().parent.parent / "seed" / "company_train_alerts.csv"

_client: MongoClient | None = None
_db: Database | None = None


def connect() -> Database | None:
    """Open the Atlas connection once; return None when Mongo is not configured or down."""
    global _client, _db
    if _db is not None:
        return _db

    uri = os.getenv("MONGODB_URI", "").strip()
    if not uri:
        log.warning("MongoDB: not connected — MONGODB_URI missing; using in-memory sample data")
        return None

    db_name = os.getenv("MONGODB_DB", "since_ai")
    log.info("MongoDB: connecting to Atlas (database=%s)…", db_name)
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=8000, appname="since-ai-server")
        client.admin.command("ping")
    except PyMongoError as exc:
        log.warning("MongoDB: not connected — %s; using in-memory sample data", exc)
        return None

    _client = client
    _db = client[db_name]
    _ensure_indexes(_db)
    _seed_if_empty(_db)
    alerts_n = _db.alerts.estimated_document_count()
    assets_n = _db.assets.estimated_document_count()
    log.info(
        "MongoDB: connected — database=%s alerts=%s assets=%s",
        _db.name,
        alerts_n,
        assets_n,
    )
    return _db


def close() -> None:
    global _client, _db
    if _client is not None:
        _client.close()
    _client = None
    _db = None


def status() -> str:
    return "connected" if _db is not None else "disabled"


def _ensure_indexes(db: Database) -> None:
    db.alerts.create_index([("asset_id", ASCENDING), ("alert_time_utc", ASCENDING)])
    db.assets.create_index("asset_id", unique=True)


def _load_seed_alerts() -> list[AlertPrediction]:
    if not SEED_ALERTS_CSV.exists():
        return SAMPLE_ALERTS
    rows: list[AlertPrediction] = []
    with SEED_ALERTS_CSV.open(newline="") as f:
        for r in csv.DictReader(f):
            correct = (r.get("correct") or "").strip().lower()
            rows.append(
                AlertPrediction(
                    asset_id=r["asset_id"],
                    alert_time_utc=r["alert_time_utc"],
                    event_class=r["event_class"],
                    fault_type=r["fault_type"],
                    confidence=float(r["confidence"]),
                    evidence=r.get("evidence") or None,
                    recommended_action=r.get("recommended_action") or None,
                    true_fault_type=r.get("true_fault_type") or None,
                    correct=True if correct == "true" else False if correct == "false" else None,
                )
            )
    return rows


def _seed_if_empty(db: Database) -> None:
    if db.alerts.estimated_document_count() == 0:
        docs = [a.model_dump(mode="json") for a in _load_seed_alerts()]
        if docs:
            db.alerts.insert_many(docs)
            log.info("MongoDB: seeded %d alerts", len(docs))
    if db.assets.estimated_document_count() == 0:
        db.assets.insert_many([a.model_dump(mode="json") for a in SAMPLE_ASSETS])
        log.info("MongoDB: seeded %d assets", len(SAMPLE_ASSETS))


def get_alerts(asset_id: str | None = None, event_class: str | None = None) -> list[AlertPrediction]:
    db = connect()
    if db is None:
        alerts = SAMPLE_ALERTS
        if asset_id:
            alerts = [a for a in alerts if a.asset_id == asset_id]
        if event_class:
            alerts = [a for a in alerts if a.event_class.value == event_class.upper()]
        return alerts

    query: dict[str, str] = {}
    if asset_id:
        query["asset_id"] = asset_id
    if event_class:
        query["event_class"] = event_class.upper()
    cursor = db.alerts.find(query, {"_id": 0}).sort([("asset_id", ASCENDING), ("alert_time_utc", ASCENDING)])
    return [AlertPrediction(**doc) for doc in cursor]


def get_assets() -> list[AssetStatus]:
    db = connect()
    if db is None:
        return SAMPLE_ASSETS
    return [AssetStatus(**doc) for doc in db.assets.find({}, {"_id": 0}).sort("asset_id", ASCENDING)]
