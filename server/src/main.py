"""FastAPI entrypoint for the Since AI product API."""

from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .models import (
    AlertPrediction,
    AssetStatus,
    CockpitResponse,
    EventClass,
    FleetSummary,
    HealthResponse,
    ScorecardResponse,
    Severity,
)
from .sample_data import (
    COCKPITS,
    SAMPLE_ALERTS,
    SAMPLE_ASSETS,
    SCORECARD,
    fleet_summary,
)

app = FastAPI(
    title="Since AI 2026 API",
    version="0.2.0",
    description="Operator cockpit API — alerts, fleet, asset diagnostics, retrofit scorecard",
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
    return HealthResponse(status="ok", service="since-ai-server")


@app.get("/api/alerts", response_model=list[AlertPrediction])
def list_alerts(
    asset_id: str | None = Query(default=None, description="Optional asset filter"),
    event_class: str | None = Query(default=None, description="MACHINE or SENSOR"),
    severity: list[Severity] | None = Query(
        default=None,
        description="Repeat to include triage bands, e.g. ?severity=SEVERE&severity=MODERATE",
    ),
) -> list[AlertPrediction]:
    alerts = SAMPLE_ALERTS
    if asset_id:
        alerts = [a for a in alerts if a.asset_id == asset_id]
    if event_class:
        alerts = [a for a in alerts if a.event_class.value == event_class.upper()]
    if severity:
        alerts = [a for a in alerts if a.severity in severity]
    return alerts


@app.get("/api/alerts/{asset_id}", response_model=list[AlertPrediction])
def alerts_for_asset(
    asset_id: str,
    severity: list[Severity] | None = Query(
        default=None,
        description="Repeat to include triage bands, e.g. ?severity=SEVERE&severity=MODERATE",
    ),
) -> list[AlertPrediction]:
    alerts = [a for a in SAMPLE_ALERTS if a.asset_id == asset_id]
    if severity:
        alerts = [a for a in alerts if a.severity in severity]
    if not alerts:
        raise HTTPException(status_code=404, detail=f"No alerts for {asset_id}")
    return alerts


@app.get("/api/assets", response_model=list[AssetStatus])
def list_assets() -> list[AssetStatus]:
    return SAMPLE_ASSETS


@app.get("/api/fleet/summary", response_model=FleetSummary)
def get_fleet_summary() -> FleetSummary:
    return fleet_summary()


@app.get("/api/cockpit/{asset_id}", response_model=CockpitResponse)
def get_cockpit(asset_id: str) -> CockpitResponse:
    if asset_id in COCKPITS:
        return COCKPITS[asset_id]

    asset = next((a for a in SAMPLE_ASSETS if a.asset_id == asset_id), None)
    if not asset:
        raise HTTPException(status_code=404, detail=f"Unknown asset {asset_id}")

    alerts = [a for a in SAMPLE_ALERTS if a.asset_id == asset_id]
    if alerts:
        top = alerts[0]
        return CockpitResponse(
            asset_id=asset_id,
            title=f"{asset.system} pump",
            diagnosis=top.fault_type.value.replace("_", " ").title(),
            event_class=top.event_class,
            confidence=top.confidence,
            severity=top.severity,
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
