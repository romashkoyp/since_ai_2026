"""Read endpoints behind the operator dashboard. All of them read the latest model run."""

from __future__ import annotations

import importlib
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import engine
from ..analysis import fleet_summary
from ..db import RunStore
from ..deps import get_store, settings_dep
from ..models import (
    AlertPrediction,
    AssetStatus,
    CockpitResponse,
    EventClass,
    FleetSummary,
    ModelInfo,
    ScorecardResponse,
)
from ..sample_data import SCORECARD
from ..settings import Settings
from ..severity import Severity

router = APIRouter(prefix="/api", tags=["dashboard"])
Store = Annotated[RunStore, Depends(get_store)]
SeverityFilter = Annotated[list[Severity] | None, Query(
    description="Repeat to include triage bands, e.g. ?severity=SEVERE&severity=MODERATE")]


@router.get("/alerts", response_model=list[AlertPrediction], summary="Alerts of the latest run")
def list_alerts(
    store: Store,
    asset_id: str | None = Query(default=None, description="Optional asset filter"),
    event_class: EventClass | None = Query(default=None, description="MACHINE or SENSOR"),
    severity: SeverityFilter = None,
) -> list[AlertPrediction]:
    record = store.latest()
    if record is None:
        return []
    return [
        a for a in record.alerts
        if (asset_id is None or a.asset_id == asset_id)
        and (event_class is None or a.event_class == event_class)
        and (not severity or a.severity in severity)
    ]


@router.get("/alerts/{asset_id}", response_model=list[AlertPrediction], summary="Alerts for one pump")
def alerts_for_asset(asset_id: str, store: Store, severity: SeverityFilter = None) -> list[AlertPrediction]:
    alerts = list_alerts(store, asset_id=asset_id, event_class=None, severity=severity)
    if not alerts:
        raise HTTPException(status_code=404, detail=f"No alerts for {asset_id}")
    return alerts


@router.get("/assets", response_model=list[AssetStatus], summary="Status tile per pump")
def list_assets(store: Store) -> list[AssetStatus]:
    record = store.latest()
    return record.assets if record else []


@router.get("/fleet/summary", response_model=FleetSummary, summary="Fleet headline counts")
def get_fleet_summary(store: Store) -> FleetSummary:
    return fleet_summary(store.latest())


@router.get("/cockpit/{asset_id}", response_model=CockpitResponse, summary="Diagnosis, trends and sandbox")
def get_cockpit(asset_id: str, store: Store) -> CockpitResponse:
    record = store.latest()
    cockpit = next((c for c in record.cockpits if c.asset_id == asset_id), None) if record else None
    if cockpit is None:
        raise HTTPException(status_code=404, detail=f"Unknown asset {asset_id}")
    return cockpit


@router.get("/scorecard", response_model=ScorecardResponse, summary="Retrofit business case (static)")
def get_scorecard() -> ScorecardResponse:
    return SCORECARD


@router.get("/model", response_model=ModelInfo, summary="Installed model and upload requirements")
def get_model(settings: Annotated[Settings, Depends(settings_dep)]) -> ModelInfo:
    eng = engine.load()
    if eng is None:
        return ModelInfo(available=False, reason=engine.unavailable_reason(), max_upload_mb=settings.max_upload_mb)
    info = eng.model_info()
    cfg = importlib.import_module("retrofit_engine.config")
    return ModelInfo(
        available=True,
        model_version=info.get("model_version"),
        physics_version=info.get("physics_version", cfg.PHYSICS_VERSION),
        classes=info.get("classes", []),
        calibrated=info.get("calibrated"),
        reason=info.get("warning"),
        required_datasheet_columns=list(cfg.REQUIRED_ASSET_COLUMNS),
        min_history_hours=cfg.MIN_HISTORY_HOURS,
        max_upload_mb=settings.max_upload_mb,
    )
