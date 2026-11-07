"""FastAPI entrypoint for the Since AI product API."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from . import db
from .models import (
    AlertPrediction,
    AssetStatus,
    CockpitResponse,
    EventClass,
    FleetSummary,
    HealthResponse,
    ScorecardResponse,
)
from .sample_data import (
    COCKPITS,
    SCORECARD,
    fleet_summary,
)


# Kaleb Routes
# from retrofit_engine.router import router as retrofit_router
# app.include_router(retrofit_router)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Logs "MongoDB: connected …" or "MongoDB: not connected …" via uvicorn.error
    db.connect()
    yield
    db.close()


app = FastAPI(
    title="Since AI 2026 API",
    version="0.3.0",
    description="Operator cockpit API — alerts, fleet, asset diagnostics, retrofit scorecard",
    lifespan=lifespan,
)

cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://localhost:3000,http://localhost,http://79.76.32.240",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="since-ai-server", database=db.status())


@app.get("/api/alerts", response_model=list[AlertPrediction])
def list_alerts(
    asset_id: str | None = Query(default=None, description="Optional asset filter"),
    event_class: str | None = Query(default=None, description="MACHINE or SENSOR"),
) -> list[AlertPrediction]:
    return db.get_alerts(asset_id=asset_id, event_class=event_class)


@app.get("/api/alerts/{asset_id}", response_model=list[AlertPrediction])
def alerts_for_asset(asset_id: str) -> list[AlertPrediction]:
    alerts = db.get_alerts(asset_id=asset_id)
    if not alerts:
        raise HTTPException(status_code=404, detail=f"No alerts for {asset_id}")
    return alerts


@app.get("/api/assets", response_model=list[AssetStatus])
def list_assets() -> list[AssetStatus]:
    return db.get_assets()


@app.get("/api/fleet/summary", response_model=FleetSummary)
def get_fleet_summary() -> FleetSummary:
    return fleet_summary(db.get_assets())


@app.get("/api/cockpit/{asset_id}", response_model=CockpitResponse)
def get_cockpit(asset_id: str) -> CockpitResponse:
    if asset_id in COCKPITS:
        return COCKPITS[asset_id]

    asset = next((a for a in db.get_assets() if a.asset_id == asset_id), None)
    if not asset:
        raise HTTPException(status_code=404, detail=f"Unknown asset {asset_id}")

    alerts = db.get_alerts(asset_id=asset_id)
    if alerts:
        top = alerts[0]
        return CockpitResponse(
            asset_id=asset_id,
            title=f"{asset.system} pump",
            diagnosis=top.fault_type.value.replace("_", " ").title(),
            event_class=top.event_class,
            confidence=top.confidence,
            safe_window="Monitor · no dedicated sandbox model yet",
            evidence=[],
            sop=[
                top.recommended_action or "Review evidence channels",
                "Keep UI read-only — no PLC writes",
            ],
            trends=[],
            sandbox_default_speed_pct=95,
            npsh_at_100=1.2,
            npsh_at_88=1.5,
            risk_at_100=0.4,
            risk_at_88=0.25,
            energy_delta_eur_day=-8.0,
            cooling_margin_pct=110,
        )

    return CockpitResponse(
        asset_id=asset_id,
        title=f"{asset.system} pump",
        diagnosis="No active fault",
        event_class=EventClass.MACHINE,
        confidence=0.99,
        safe_window="Healthy envelope",
        evidence=[],
        sop=["Continue normal watch", "Standby verification on schedule"],
        trends=[],
        sandbox_default_speed_pct=100,
        npsh_at_100=2.0,
        npsh_at_88=2.3,
        risk_at_100=0.05,
        risk_at_88=0.04,
        energy_delta_eur_day=0.0,
        cooling_margin_pct=120,
    )


@app.get("/api/scorecard", response_model=ScorecardResponse)
def get_scorecard() -> ScorecardResponse:
    return SCORECARD
