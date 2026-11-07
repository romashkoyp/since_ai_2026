"""predict(): datasheet + telemetry (+ optional baseline) -> alerts in the template format.

    1-minute summaries -> each pump's normal (from the baseline / first 24 h) -> Joice's physics indicators
    -> Joice's detector decides WHEN -> at each alert Joice's rule verdict + ML model -> hybrid decides WHAT
"""
from __future__ import annotations

import hashlib
import json
import math
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C
from ._vendor import baselines as B
from .features import class_of, features_at, snapshot_ratios, vibration_features
from .inputs import UTC_NS, merge_baseline, prepare_datasheet, to_minutes, ts
from .model import HybridModel
from .physics import diag2

warnings.filterwarnings("ignore")
MODEL_DIR = Path(__file__).resolve().parent / "model"
_MODEL = {"obj": None, "error": None, "loaded": False}


def get_model(model_dir: str | Path | None = None) -> HybridModel | None:
    """load the trained hybrid once (from retrofit_engine/model/); None if no model is installed"""
    if model_dir is not None:
        return HybridModel(model_dir)
    if not _MODEL["loaded"]:
        _MODEL["loaded"] = True
        if (MODEL_DIR / "diagnostician.joblib").exists():
            _MODEL["obj"] = HybridModel(MODEL_DIR)                  # raises on a feature-version mismatch
        else:
            _MODEL["error"] = f"no model in {MODEL_DIR}; running Joice's rules only"
    return _MODEL["obj"]


def model_info() -> dict:
    m = get_model()
    return m.info() if m is not None else {"model_version": "rules-only", "warning": _MODEL["error"]}


# ------------------------------------------------------------------ internal steps
def _physics_frame(assets, feat, ctx, snaps):
    zf = B.zscores(B.regime_frame(feat, assets))
    zf["window_start_utc"] = pd.to_datetime(zf["window_start_utc"], utc=True).astype(UTC_NS)
    rows = []
    if ctx is not None and len(ctx):
        c = ctx.copy()
        c["t"] = ts(c["timestamp_utc"]); c["asset_id"] = c["asset_id"].astype(str)
        for k in ("sea_state_hs_m", "suction_static_head_m"):
            c[k] = pd.to_numeric(c[k], errors="coerce") if k in c else np.nan
        rows.append(c[["asset_id", "t", "sea_state_hs_m", "suction_static_head_m"]])
    have = set(rows[0]["asset_id"]) if rows else set()
    t0 = feat["window_start_utc"].min()
    rows.append(pd.DataFrame({"asset_id": sorted(set(assets["asset_id"]) - have), "t": t0,
                              "sea_state_hs_m": np.nan, "suction_static_head_m": np.nan}))
    ctx = pd.concat(rows, ignore_index=True)
    ctx["t"] = ctx["t"].astype(UTC_NS)
    snapf = snapshot_ratios(vibration_features(snaps, assets))
    return diag2.prep(zf, ctx, snapf, assets)


def _resolve_conflicts(rows):
    """never drop a detector alert; undo an ML override that would clash (repeat < 12 h, or other guess < 5 min)"""
    out, last_any, last_type = [], {}, {}
    for t, orig, new in sorted(rows, key=lambda x: (x[1]["asset_id"], x[0])):
        a = orig["asset_id"]
        if new["fault_type"] != orig["fault_type"]:
            ft = new["fault_type"]
            repeat = ft != "CAVITATION" and (a, ft) in last_type and t - last_type[(a, ft)] < B.REFRACTORY
            burst = a in last_any and t - last_any[a][0] <= pd.Timedelta(minutes=5) and last_any[a][1] != ft
            if repeat or burst:
                new = dict(orig, decided_by="RULE (override undone: clash)")
        out.append(new)
        last_any[a] = (t, new["fault_type"]); last_type[(a, new["fault_type"])] = t
    return out


def _hybrid(zp, assets, rule_alerts, model):
    A = assets.set_index("asset_id")
    rows = []
    for aid, g in zp.groupby("asset_id", sort=False):
        al = rule_alerts[rule_alerts["asset_id"] == aid]
        if al.empty:
            continue
        g = g.sort_values("window_start_utc").reset_index(drop=True)
        tend = g["window_start_utc"] + pd.Timedelta(minutes=1)
        feats, idx, times = [], [], {}
        for i, r in al.iterrows():
            t = ts(pd.Series([r.alert_time_utc]))[0]; times[i] = t
            j = int(tend.searchsorted(t, side="right") - 1)
            if model is not None and j >= 0:
                feats.append(features_at(g, j, A.loc[aid])); idx.append(i)
        ml = model.diagnose(pd.DataFrame(feats, index=idx)) if (model is not None and feats) else pd.DataFrame()
        for i, r in al.iterrows():
            orig = dict(r.to_dict(), rule_fault_type=r.fault_type, ml_fault_type=None, ml_confidence=None, decided_by="RULE")
            new = dict(orig)
            if i in ml.index:
                m_type, conf = ml.at[i, "ml_type"], float(ml.at[i, "ml_conf"])
                orig.update(ml_fault_type=m_type, ml_confidence=round(conf, 3)); new.update(orig)
                if m_type == r.fault_type and conf >= C.MIN_CONF:
                    new.update(confidence=round(max(float(r.confidence), conf), 3), decided_by="RULE+ML agree",
                               evidence=f"{r.evidence} | ML agrees ({conf:.2f})")
                elif m_type == r.fault_type:
                    pass                                             # agrees, but not confidently: rule stands
                elif r.fault_type in C.RULE_PRIORITY:
                    new.update(decided_by="RULE (priority type)")
                elif m_type != "NO_FAULT" and conf >= C.MIN_CONF:
                    new.update(fault_type=m_type, event_class=class_of(m_type), confidence=round(conf, 3),
                               recommended_action=C.ACTIONS.get(m_type, r.recommended_action), decided_by="ML",
                               evidence=f"ML {m_type} ({conf:.2f}) overrides rule {r.fault_type}; rule evidence: {r.evidence}")
            rows.append((times[i], orig, new))
    return pd.DataFrame(_resolve_conflicts(rows))


def _clean(v):
    """JSON-safe values"""
    if isinstance(v, (np.floating, float)):
        return None if math.isnan(float(v)) else float(v)
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.bool_):
        return bool(v)
    if isinstance(v, pd.Timestamp):
        return v.strftime("%Y-%m-%dT%H:%M:%SZ")
    return v


# ------------------------------------------------------------------ public
def predict(datasheet: pd.DataFrame, telemetry: pd.DataFrame, baseline: pd.DataFrame | None = None,
            context: pd.DataFrame | None = None, snapshots: pd.DataFrame | None = None,
            use_ml: bool = True, model_dir: str | Path | None = None) -> dict:
    """Run Joice's physics + the hybrid model on uploaded tables.

    datasheet : one row per pump (asset_id, control, motor_rated_rpm, pump_rated_flow_m3_h, pump_rated_head_m,
                pump_shutoff_head_m, npsh3_at_bep_m, fluid; optional extras, see config.py)
    telemetry : the period to monitor; raw readings (asset_id, timestamp_utc, sensor columns) or 1-minute summaries
    baseline  : optional, same format; a healthy period BEFORE the telemetry (>= 24 h) that defines "normal"
    context   : optional (asset_id, timestamp_utc, sea_state_hs_m, suction_static_head_m)
    snapshots : optional vibration waveforms (asset_id, timestamp_utc, sample_rate_hz, rpm_at_capture, samples)
    Returns a JSON-ready dict: alerts (template format + extras), pumps, summary, notes.
    """
    t_start = time.time(); notes = []
    tele = to_minutes(telemetry, datasheet, "telemetry", notes)
    base = to_minutes(baseline, datasheet, "baseline", notes) if baseline is not None else None
    feat, mon_from = merge_baseline(base, tele, notes)
    assets = prepare_datasheet(datasheet, feat, notes)
    if assets.empty:
        raise ValueError("no pump has both a datasheet row and telemetry")
    feat = feat[feat["asset_id"].isin(assets["asset_id"])]
    if snapshots is not None:
        snapshots = snapshots.copy(); snapshots["asset_id"] = snapshots["asset_id"].astype(str)
        if isinstance(snapshots["samples"].iloc[0], str):            # JSON-encoded arrays from CSV
            snapshots["samples"] = snapshots["samples"].map(lambda s: np.asarray(json.loads(s), dtype=float))
    elif any(t in ("T1_RETROFIT", "T2_FULL") for t in assets["instrumentation_tier"]):
        notes.append("no vibration snapshots: bearing / misalignment / imbalance diagnosis is weaker (bearing index unavailable)")

    model = get_model(model_dir) if use_ml else None
    if use_ml and model is None:
        notes.append(_MODEL["error"] or "no model loaded; rules only")

    zp = _physics_frame(assets, feat, context, snapshots)
    rule_alerts = diag2.detect(zp, assets)
    al = _hybrid(zp, assets, rule_alerts, model) if len(rule_alerts) else pd.DataFrame(columns=C.TEMPLATE_COLUMNS)

    if len(al) and mon_from is not None:                             # report only the monitored period
        t = ts(al["alert_time_utc"]); start = al["asset_id"].map(mon_from)
        al = al[start.isna() | (t >= start)]
    al = al.reset_index(drop=True)
    if len(al):
        al.insert(0, "alert_id", [hashlib.sha1(f"{a}|{t}|{f}".encode()).hexdigest()[:12]
                                  for a, t, f in zip(al.asset_id, al.alert_time_utc, al.fault_type)])

    pumps = []
    for _, a in assets.iterrows():
        g = feat[feat.asset_id == a.asset_id]
        span = (g.window_start_utc.max() - g.window_start_utc.min()).total_seconds() / 3600
        mf = mon_from.get(a.asset_id) if mon_from is not None else None
        pumps.append({"asset_id": a.asset_id, "instrumentation_tier": a.instrumentation_tier, "control": a.control,
                      "sensors": str(a.channels_available).split("|"), "hours_of_data": round(span, 1),
                      "monitored_from_utc": _clean(mf) if mf is not None else None,
                      "alerts": int((al.asset_id == a.asset_id).sum()) if len(al) else 0})
        if span < C.MIN_HISTORY_HOURS:
            notes.append(f"{a.asset_id}: only {span:.1f} h of data; alerts need more than ~{C.MIN_HISTORY_HOURS} h")

    extra = ["alert_id"] + C.TEMPLATE_COLUMNS + ["decided_by", "rule_fault_type", "ml_fault_type", "ml_confidence"]
    alerts = [{k: _clean(r.get(k)) for k in extra} for r in al.to_dict("records")] if len(al) else []
    by_type = al["fault_type"].value_counts().to_dict() if len(al) else {}
    summary = {"pumps": len(assets), "alerts": len(alerts), "by_fault_type": {k: int(v) for k, v in by_type.items()},
               "ml_overrides": int((al["decided_by"] == "ML").sum()) if len(al) else 0,
               "model_version": model.version if model is not None else "rules-only",
               "physics_version": C.PHYSICS_VERSION, "processing_seconds": round(time.time() - t_start, 1)}
    return {"alerts": alerts, "pumps": pumps, "summary": summary, "notes": notes}


def to_template_csv(result: dict) -> str:
    """the alerts of predict() as the organisers' template CSV"""
    df = pd.DataFrame(result["alerts"], columns=["alert_id"] + C.TEMPLATE_COLUMNS)
    return df[C.TEMPLATE_COLUMNS].to_csv(index=False)
