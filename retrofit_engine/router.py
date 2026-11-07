"""FastAPI router. Mount it in your existing app:

    from retrofit_engine.router import router as retrofit_router
    app.include_router(retrofit_router)

Endpoints (multipart file uploads; CSV, parquet or JSON):
    GET  /retrofit/info          model version, required datasheet columns, limits
    POST /retrofit/analyze       -> JSON {alerts, pumps, summary, notes}
    POST /retrofit/analyze/csv   -> the alerts as the organisers' template CSV (download)
"""
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from . import config as C
from .engine import model_info, predict, to_template_csv
from .inputs import read_table

router = APIRouter(prefix="/retrofit", tags=["retrofit"])


def _load(f: Optional[UploadFile], label: str):
    if f is None or not f.filename:
        return None
    try:
        return read_table(f.file.read(), f.filename)
    except Exception as e:
        raise HTTPException(422, f"could not read {label} file '{f.filename}': {e}")


def _run(datasheet, telemetry, baseline, context, snapshots, use_ml):
    try:
        return predict(_load(datasheet, "datasheet"), _load(telemetry, "telemetry"), _load(baseline, "baseline"),
                       _load(context, "context"), _load(snapshots, "snapshots"), use_ml=use_ml)
    except HTTPException:
        raise
    except ValueError as e:                                  # bad input: tell the user what is wrong
        raise HTTPException(422, str(e))


@router.get("/info")
def info():
    return {"model": model_info(), "required_datasheet_columns": C.REQUIRED_ASSET_COLUMNS,
            "optional_datasheet_columns": sorted(C.ASSET_DEFAULTS) + ["channels_available", "instrumentation_tier"],
            "control_types": sorted(C.CONTROLS), "min_history_hours": C.MIN_HISTORY_HOURS,
            "output_columns": C.TEMPLATE_COLUMNS}


# plain `def` (not async): FastAPI runs it in a worker thread, so the analysis does not block the server
@router.post("/analyze")
def analyze(datasheet: UploadFile = File(...), telemetry: UploadFile = File(...),
            baseline: Optional[UploadFile] = File(None), context: Optional[UploadFile] = File(None),
            snapshots: Optional[UploadFile] = File(None), use_ml: bool = Form(True)):
    return _run(datasheet, telemetry, baseline, context, snapshots, use_ml)


@router.post("/analyze/csv")
def analyze_csv(datasheet: UploadFile = File(...), telemetry: UploadFile = File(...),
                baseline: Optional[UploadFile] = File(None), context: Optional[UploadFile] = File(None),
                snapshots: Optional[UploadFile] = File(None), use_ml: bool = Form(True)):
    res = _run(datasheet, telemetry, baseline, context, snapshots, use_ml)
    return Response(to_template_csv(res), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=alerts.csv"})
