"""Upload pump data, run the trained model, keep the result as the dashboard's latest run."""

from __future__ import annotations

import logging
from pathlib import PurePath
from typing import Annotated

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response

from .. import engine
from ..analysis import AnalysisInputs, alerts_csv, run_analysis
from ..db import RunStore
from ..deps import get_store, settings_dep
from ..models import AnalysisRunSummary
from ..settings import Settings

log = logging.getLogger("uvicorn.error")
router = APIRouter(prefix="/api/analyses", tags=["analyses"])
Store = Annotated[RunStore, Depends(get_store)]
Config = Annotated[Settings, Depends(settings_dep)]
ALLOWED_SUFFIXES = {".csv", ".parquet", ".json"}
_CHUNK = 1 << 20


def _read_upload(upload: UploadFile | None, label: str, settings: Settings) -> pd.DataFrame | None:
    """Read one optional upload into a DataFrame, enforcing type and size limits."""
    if upload is None or not upload.filename:
        return None
    name = upload.filename
    if PurePath(name).suffix.lower() not in ALLOWED_SUFFIXES:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                            f"{label} file '{name}': use CSV, parquet or JSON")
    buf = bytearray()
    while chunk := upload.file.read(_CHUNK):
        buf += chunk
        if len(buf) > settings.max_upload_bytes:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE,
                                f"{label} file '{name}' is larger than {settings.max_upload_mb:g} MB")
    if not buf:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"{label} file '{name}' is empty")
    try:
        return engine.require().read_table(bytes(buf), name)
    except engine.EngineUnavailableError:
        raise
    except Exception as exc:  # noqa: BLE001 - parser errors vary by format; all are user input problems
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"could not read {label} file '{name}': {exc}")


def _summary_or_404(store: RunStore, run_id: str) -> AnalysisRunSummary:
    record = store.get(run_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown analysis run {run_id}")
    return record.summary


# plain `def`: FastAPI runs it in a worker thread, so the CPU-bound analysis does not block the event loop
@router.post("", response_model=AnalysisRunSummary, status_code=status.HTTP_201_CREATED,
             summary="Upload pump data and run the model")
def create_analysis(
    store: Store,
    settings: Config,
    datasheet: Annotated[UploadFile, File(description="One row per pump (asset_id, control, ratings…)")],
    telemetry: Annotated[UploadFile, File(description="Period to monitor: raw readings or 1-minute summaries")],
    baseline: Annotated[UploadFile | None, File(description="Healthy period before the telemetry (≥ 24 h)")] = None,
    context: Annotated[UploadFile | None, File(description="Sea state / suction head")] = None,
    snapshots: Annotated[UploadFile | None, File(description="Vibration waveforms (parquet)")] = None,
    events: Annotated[UploadFile | None, File(description="Optional ground truth to score the alerts")] = None,
    use_ml: Annotated[bool, Form(description="Use the ML diagnostician on top of the physics rules")] = True,
) -> AnalysisRunSummary:
    try:
        inputs = AnalysisInputs(
            datasheet=_read_upload(datasheet, "datasheet", settings),
            telemetry=_read_upload(telemetry, "telemetry", settings),
            baseline=_read_upload(baseline, "baseline", settings),
            context=_read_upload(context, "context", settings),
            snapshots=_read_upload(snapshots, "snapshots", settings),
            events=_read_upload(events, "events", settings),
        )
        if inputs.datasheet is None or inputs.telemetry is None:
            raise ValueError("both a datasheet file and a telemetry file are required")
        label = " + ".join(f.filename for f in (datasheet, telemetry) if f is not None and f.filename)
        record = run_analysis(inputs, settings, source="upload", label=label, use_ml=use_ml)
    except engine.EngineUnavailableError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"model engine unavailable: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            f"the uploaded data is missing a column the model needs: {exc}") from exc
    store.save(record)
    log.info("Analysis %s: %d pumps, %d alerts in %.1fs", record.summary.run_id, record.summary.pumps,
             record.summary.alerts, record.summary.processing_seconds)
    return record.summary


@router.get("", response_model=list[AnalysisRunSummary], summary="Recent runs, newest first")
def list_analyses(store: Store, limit: int = Query(default=20, ge=1, le=100)) -> list[AnalysisRunSummary]:
    return store.list(limit)


@router.get("/latest", response_model=AnalysisRunSummary, summary="The run the dashboard shows")
def latest_analysis(store: Store) -> AnalysisRunSummary:
    record = store.latest()
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No analysis run yet")
    return record.summary


@router.get("/{run_id}", response_model=AnalysisRunSummary, summary="One run")
def get_analysis(run_id: str, store: Store) -> AnalysisRunSummary:
    return _summary_or_404(store, run_id)


@router.get("/{run_id}/alerts.csv", summary="Alerts in the organisers' template CSV",
            response_class=Response, responses={200: {"content": {"text/csv": {}}}})
def download_alerts(run_id: str, store: Store) -> Response:
    record = store.get(run_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown analysis run {run_id}")
    return Response(alerts_csv(record.alerts), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="alerts_{run_id[:8]}.csv"'})
