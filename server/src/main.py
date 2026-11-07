"""FastAPI entrypoint for the Since AI product API."""

from __future__ import annotations

import importlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from . import db, engine
from .models import HealthResponse
from .routers import analyses, dashboard
from .settings import get_settings

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Logs "MongoDB: connected …" or "MongoDB: not connected …" via uvicorn.error
    app.state.store = db.open_store(settings)
    db.ensure_seed(app.state.store, settings.seed_run_path)
    yield
    app.state.store.close()


app = FastAPI(
    title="Since AI 2026 API",
    version="0.4.0",
    description="Operator cockpit API — runs the trained hybrid model (physics rules + ML) on uploaded pump "
                "data and serves alerts, fleet status, per-pump diagnostics and the retrofit scorecard",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboard.router)
app.include_router(analyses.router)

# Kaleb's stateless engine endpoints (/retrofit/info, /retrofit/analyze, /retrofit/analyze/csv)
if engine.load() is not None:
    app.include_router(importlib.import_module("retrofit_engine.router").router)


@app.get("/health", response_model=HealthResponse, tags=["meta"])
def health(request: Request) -> HealthResponse:
    store = getattr(request.app.state, "store", None)
    eng = engine.load()
    return HealthResponse(
        status="ok",
        service="since-ai-server",
        database="connected" if store is not None and store.backend == "mongodb" else "disabled",
        model=eng.model_info().get("model_version") if eng is not None else "unavailable",
    )
