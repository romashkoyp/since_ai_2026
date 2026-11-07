"""Upload pump data, run the trained model in the background, keep the result as the dashboard's latest run."""

from __future__ import annotations

import importlib
from pathlib import PurePath
from typing import Annotated

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response

from .. import engine
from ..analysis import AnalysisInputs, alerts_csv, run_analysis
from ..db import RunStore
from ..deps import get_jobs, get_store, settings_dep
from ..jobs import JobRunner
from ..models import AnalysisJob, AnalysisRecord, AnalysisRunSummary
from ..settings import Settings

router = APIRouter(prefix="/api/analyses", tags=["analyses"])
Store = Annotated[RunStore, Depends(get_store)]
Jobs = Annotated[JobRunner, Depends(get_jobs)]
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


def _check_datasheet_columns(sheet: pd.DataFrame) -> None:
    """Fail fast (before queueing) on the most common upload mistake."""
    required = importlib.import_module("retrofit_engine.config").REQUIRED_ASSET_COLUMNS
    present = {str(c).strip() for c in sheet.columns}
    missing = [c for c in required if c not in present]
    if missing:
        raise ValueError(f"datasheet is missing columns {missing}; required: {list(required)}")


# plain `def`: reading / validating uploads is blocking I/O, so FastAPI runs it in a worker thread
@router.post("", response_model=AnalysisJob, status_code=status.HTTP_202_ACCEPTED,
             summary="Upload pump data; the model runs in the background (poll the job)")
def create_analysis(
    response: Response,
    store: Store,
    jobs: Jobs,
    settings: Config,
    datasheet: Annotated[UploadFile, File(description="One row per pump (asset_id, control, ratings…)")],
    telemetry: Annotated[UploadFile, File(description="Period to monitor: raw readings or 1-minute summaries")],
    baseline: Annotated[UploadFile | None, File(description="Healthy period before the telemetry (≥ 24 h)")] = None,
    context: Annotated[UploadFile | None, File(description="Sea state / suction head")] = None,
    snapshots: Annotated[UploadFile | None, File(description="Vibration waveforms (parquet)")] = None,
    events: Annotated[UploadFile | None, File(description="Optional ground truth to score the alerts")] = None,
    use_ml: Annotated[bool, Form(description="Use the ML diagnostician on top of the physics rules")] = True,
) -> AnalysisJob:
    """Files are checked now (type, size, required columns -> 415 / 413 / 422); the model run is queued and the
    answer is 202 with a job. Poll GET /api/analyses/jobs/{job_id} until status is completed or failed."""
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
        _check_datasheet_columns(inputs.datasheet)
    except engine.EngineUnavailableError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"model engine unavailable: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    label = " + ".join(f.filename for f in (datasheet, telemetry) if f is not None and f.filename)

    def work() -> AnalysisRecord:
        record = run_analysis(inputs, settings, source="upload", label=label, use_ml=use_ml)
        store.save(record)
        return record

    job = jobs.submit(label, work)
    response.headers["Location"] = f"/api/analyses/jobs/{job.job_id}"
    return job


@router.get("/jobs/{job_id}", response_model=AnalysisJob, summary="Progress of an upload's model run")
def get_job(job_id: str, jobs: Jobs) -> AnalysisJob:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown job {job_id} (jobs are kept until the server restarts)")
    return job


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
