"""FastAPI entrypoint for the Since AI product API."""

from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .models import AlertPrediction, AssetStatus, HealthResponse
from .sample_data import SAMPLE_ALERTS, SAMPLE_ASSETS

app = FastAPI(
    title="Since AI 2026 API",
    version="0.1.0",
    description="Sample backend serving alert predictions aligned with shared/contracts.schema.json",
)

cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://localhost:3000,http://localhost",
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
) -> list[AlertPrediction]:
    alerts = SAMPLE_ALERTS
    if asset_id:
        alerts = [a for a in alerts if a.asset_id == asset_id]
    if event_class:
        alerts = [a for a in alerts if a.event_class.value == event_class.upper()]
    return alerts


@app.get("/api/alerts/{asset_id}", response_model=list[AlertPrediction])
def alerts_for_asset(asset_id: str) -> list[AlertPrediction]:
    alerts = [a for a in SAMPLE_ALERTS if a.asset_id == asset_id]
    if not alerts:
        raise HTTPException(status_code=404, detail=f"No alerts for {asset_id}")
    return alerts


@app.get("/api/assets", response_model=list[AssetStatus])
def list_assets() -> list[AssetStatus]:
    return SAMPLE_ASSETS
