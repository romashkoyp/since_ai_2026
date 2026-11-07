"""Run the trained hybrid model (retrofit_engine) on uploaded tables and shape its output for the dashboard.

    datasheet + telemetry (+ baseline, context, snapshots)  ->  retrofit_engine.predict()
        -> alerts (contract AlertPrediction + model provenance)
        -> per pump: status tile (Fleet screen) and cockpit (Pump screen: diagnosis, evidence, trends, sandbox)
    optional ground-truth events -> each alert gets true_fault_type / correct (Pass / Fail in the UI)
"""

from __future__ import annotations

import re
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from . import engine
from .fault_guide import guide_for
from .models import (
    AlertPrediction,
    AnalysisRecord,
    AnalysisRunSummary,
    AssetStatus,
    CockpitResponse,
    EventClass,
    EvidenceRow,
    FleetSummary,
    PumpSeverity,
    StoredAlert,
    TrendPoint,
    TrendSeries,
)
from .sandbox import HEALTHY_RISK, latest_state, simulate
from .settings import Settings

# Analyses are CPU-bound (pandas + LightGBM); run one at a time so parallel uploads cannot starve the API.
_LOCK = threading.Lock()

ISO = "%Y-%m-%dT%H:%M:%SZ"
TREND_MAX_POINTS = 168  # one week of hourly points per series
# Ground-truth matching = the team's labelling rule (joice_physics_rules/build_training_table.py true_label):
# a fault is active from 30 min before onset to 2 h after end; when several are active, the latest onset wins.
TRUTH_BEFORE_ONSET = pd.Timedelta(minutes=30)
TRUTH_AFTER_END = pd.Timedelta(hours=2)
OPEN_ENDED = pd.Timestamp("2200-01-01", tz="UTC")

CHANNELS: dict[str, tuple[str, str]] = {
    "motor_speed_rpm": ("Motor speed", "rpm"),
    "motor_current_a": ("Motor current", "A"),
    "motor_power_kw": ("Motor power", "kW"),
    "suction_pressure_kpa": ("Suction pressure", "kPa"),
    "discharge_pressure_kpa": ("Discharge pressure", "kPa"),
    "flow_m3_h": ("Flow", "m³/h"),
    "fluid_temp_c": ("Fluid temperature", "°C"),
    "bearing_temp_c": ("Bearing temp", "°C"),
    "motor_winding_temp_c": ("Winding temperature", "°C"),
    "vibration_rms_mm_s": ("Vibration RMS", "mm/s"),
    "vibration_accel_rms_g": ("Vibration acceleration", "g"),
    "vibration_crest_factor": ("Crest factor", ""),
    "valve_position_pct": ("Valve position", "%"),
}
_MECHANICAL = {"BEARING_WEAR", "MISALIGNMENT", "IMBALANCE"}
_MECH_TRENDS = ["vibration_rms_mm_s", "vibration_accel_rms_g", "bearing_temp_c", "motor_current_a"]
_HYDRAULIC_TRENDS = ["discharge_pressure_kpa", "suction_pressure_kpa", "flow_m3_h", "motor_power_kw", "motor_current_a"]
_EVIDENCE_Z = re.compile(r"\b(" + "|".join(CHANNELS) + r")\b[^;,|]*?z=([+-]?\d+(?:\.\d+)?)")
_STATUS = {PumpSeverity.ACT_NOW: "alert", PumpSeverity.ATTENTION: "alert", PumpSeverity.SENSOR: "sensor_issue",
           PumpSeverity.OK: "healthy"}
_NUMERIC_SHEET = ["motor_rated_rpm", "pump_rated_flow_m3_h", "npsh3_at_bep_m", "motor_rated_kw",
                  "motor_rated_current_a", "vibration_alarm_mm_s", "min_speed_ratio"]


@dataclass
class AnalysisInputs:
    datasheet: pd.DataFrame
    telemetry: pd.DataFrame
    baseline: pd.DataFrame | None = None
    context: pd.DataFrame | None = None
    snapshots: pd.DataFrame | None = None
    events: pd.DataFrame | None = None  # optional ground truth: asset_id, fault_type, onset_utc[, end_utc]


# ------------------------------------------------------------------ helpers
def _ts(value) -> pd.Timestamp:
    t = pd.Timestamp(value)
    return t.tz_convert("UTC") if t.tzinfo else t.tz_localize("UTC")


def _iso(value) -> str:
    return _ts(value).strftime(ISO)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime(ISO)


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def _normalise_sheet(sheet: pd.DataFrame) -> pd.DataFrame:
    s = sheet.copy()
    s.columns = [str(c).strip() for c in s.columns]
    if "asset_id" not in s:
        raise ValueError("datasheet: needs an 'asset_id' column")
    s["asset_id"] = s["asset_id"].astype(str)
    for c in _NUMERIC_SHEET:
        if c in s:
            s[c] = pd.to_numeric(s[c], errors="coerce")
    return s.drop_duplicates("asset_id").set_index("asset_id", drop=False)


def _only_known_pumps(table: pd.DataFrame | None, pumps: set[str], label: str,
                      notes: list[str]) -> pd.DataFrame | None:
    """Drop rows for pumps missing from the datasheet (the engine cannot look up their ratings)."""
    if table is None or "asset_id" not in table:
        return table
    ids = table["asset_id"].astype(str)
    unknown = sorted(set(ids) - pumps)
    if unknown:
        notes.append(f"{label}: rows for pumps not in the datasheet were ignored ({', '.join(unknown)})")
    kept = table[ids.isin(pumps)]
    return kept if len(kept) else None


def _text(row: pd.Series, key: str) -> str | None:
    v = row.get(key)
    return None if v is None or (isinstance(v, float) and np.isnan(v)) or str(v).strip() == "" else str(v).strip()


def _num(row: pd.Series, key: str) -> float | None:
    v = row.get(key)
    return None if v is None or pd.isna(v) else float(v)


# ------------------------------------------------------------------ ground truth
def _label_alerts(alerts: list[StoredAlert], events: pd.DataFrame) -> None:
    missing = [c for c in ("asset_id", "fault_type", "onset_utc") if c not in events]
    if missing:
        raise ValueError(f"events: missing columns {missing}; need asset_id, fault_type, onset_utc (end_utc optional)")
    ev = pd.DataFrame({
        "asset_id": events["asset_id"].astype(str),
        "fault_type": events["fault_type"].astype(str),
        "onset": pd.to_datetime(events["onset_utc"], utc=True, format="ISO8601"),
        "end": pd.to_datetime(events["end_utc"], utc=True, format="ISO8601") if "end_utc" in events else pd.NaT,
    })
    ev["end"] = ev["end"].fillna(OPEN_ENDED)  # fault still going at the end of the data
    for a in alerts:
        t = _ts(a.alert_time_utc)
        active = ev[(ev.asset_id == a.asset_id) & (ev.onset - TRUTH_BEFORE_ONSET <= t)
                    & (t <= ev.end + TRUTH_AFTER_END)]
        # the fault happening at that moment = the most recent one to start
        a.true_fault_type = active.sort_values("onset").iloc[-1].fault_type if len(active) else "NO_FAULT"
        a.correct = a.true_fault_type == a.fault_type.value


# ------------------------------------------------------------------ per pump
def _top_alert(active: list[StoredAlert]) -> StoredAlert | None:
    """most severe open alert; the most recent one when tied"""
    if not active:
        return None
    return min(active, key=lambda a: (guide_for(a.fault_type.value).rank, -_ts(a.alert_time_utc).value))


def _evidence_rows(evidence: str | None) -> list[EvidenceRow]:
    rows, seen = [], set()
    for channel, z in _EVIDENCE_Z.findall(evidence or ""):
        if channel in seen:
            continue
        seen.add(channel)
        sigma = float(z)
        rows.append(EvidenceRow(channel=CHANNELS[channel][0], sigma=sigma,
                                note=f"{'Above' if sigma > 0 else 'Below'} this pump's own normal"))
    return rows


def _trend_channels(top: StoredAlert | None, available: list[str]) -> list[str]:
    picked = [c for c, _ in _EVIDENCE_Z.findall(top.evidence or "") if c in available] if top else []
    defaults = _MECH_TRENDS if top is not None and top.fault_type.value in _MECHANICAL else _HYDRAULIC_TRENDS
    return list(dict.fromkeys(picked + [c for c in defaults if c in available]))[:3]


def _trends(minutes: pd.DataFrame, channels: list[str], sheet: pd.Series) -> list[TrendSeries]:
    cols = [f"{c}__mean" for c in channels]
    hourly = minutes.set_index("window_start_utc")[cols].resample("1h").mean().tail(TREND_MAX_POINTS)
    out = []
    for c in channels:
        s = hourly[f"{c}__mean"].dropna()
        if s.empty:
            continue
        name, unit = CHANNELS[c]
        threshold = _num(sheet, "vibration_alarm_mm_s") if c == "vibration_rms_mm_s" else None
        out.append(TrendSeries(name=name, unit=unit, threshold=threshold,
                               points=[TrendPoint(t=t.strftime(ISO), value=round(float(v), 3)) for t, v in s.items()]))
    return out


def _load_pct(minutes: pd.DataFrame, sheet: pd.Series, mode: str) -> float:
    if mode != "RUNNING":
        return 0.0
    tail = minutes.tail(15)

    def last(col: str) -> float | None:
        return float(tail[col].median()) if col in tail and tail[col].notna().any() else None

    power, rated_kw = last("motor_power_kw__mean"), _num(sheet, "motor_rated_kw")
    if power is not None and rated_kw:
        return round(100 * power / rated_kw, 1)
    current, rated_a = last("motor_current_a__mean"), _num(sheet, "motor_rated_current_a")
    if current is not None and rated_a:
        return round(100 * current / rated_a, 1)
    speed, rated_rpm = last("motor_speed_rpm__mean"), _num(sheet, "motor_rated_rpm")
    if speed is not None and rated_rpm:
        return round(100 * speed / rated_rpm, 1)
    return 0.0


def _pump_views(pump: dict, minutes: pd.DataFrame, sheet: pd.Series, alerts: list[StoredAlert],
                settings: Settings) -> tuple[AssetStatus, CockpitResponse]:
    asset_id = pump["asset_id"]
    last_ts = minutes["window_start_utc"].max() + pd.Timedelta(minutes=1)
    since = last_ts - pd.Timedelta(hours=settings.active_alert_hours)
    active = [a for a in alerts if a.asset_id == asset_id and _ts(a.alert_time_utc) >= since]
    top = _top_alert(active)
    guide = guide_for(top.fault_type.value) if top else None
    severity = guide.severity if guide else PumpSeverity.OK

    mode = str(minutes["operating_mode"].tail(15).mode().iat[0]) if "operating_mode" in minutes else "UNKNOWN"
    system = _text(sheet, "system") or _text(sheet, "profile") or f"{pump['control']} pump"
    asset = AssetStatus(
        asset_id=asset_id,
        site=_text(sheet, "site") or "Unassigned site",
        system=system,
        tier=str(pump["instrumentation_tier"]).split("_")[0],
        status=_STATUS[severity],
        mode=mode,
        load_pct=_load_pct(minutes, sheet, mode),
        open_alerts=len(active),
        fault_summary=guide.plain_name if guide else None,
        severity=severity,
        last_data_utc=last_ts.strftime(ISO),
    )

    available = [c for c in CHANNELS if f"{c}__mean" in minutes and minutes[f"{c}__mean"].notna().any()]
    is_machine = top is not None and top.event_class == EventClass.MACHINE
    sb = simulate(latest_state(minutes), sheet, top.fault_type.value if top else None,
                  top.confidence if top else None, is_machine,
                  settings.energy_price_eur_kwh, settings.cooling_min_flow_fraction)
    hours = f"{settings.active_alert_hours:g}"
    cockpit = CockpitResponse(
        asset_id=asset_id,
        title=system,
        diagnosis=guide.plain_name if guide else "No active fault",
        event_class=top.event_class if top else EventClass.MACHINE,
        confidence=top.confidence if top else round(1 - HEALTHY_RISK, 2),
        severity=top.severity if top else None,
        safe_window=guide.urgency_text if guide else f"No open alerts in the last {hours} h of data.",
        evidence=_evidence_rows(top.evidence) if top else [],
        sop=list(guide.what_to_do) if guide else ["Continue normal watch.", "Re-run the analysis with new data."],
        trends=_trends(minutes, _trend_channels(top, available), sheet),
        sandbox_default_speed_pct=100,
        npsh_at_100=sb.npsh_at_100,
        npsh_at_88=sb.npsh_at_88,
        risk_at_100=sb.risk_at_100,
        risk_at_88=sb.risk_at_88,
        energy_delta_eur_day=sb.energy_delta_eur_day,
        cooling_margin_pct=sb.cooling_margin_pct,
        fault_type=top.fault_type if top else None,
        rated_rpm=_num(sheet, "motor_rated_rpm"),
        cooling_safe_flow_m3h=sb.cooling_safe_flow_m3h,
        sandbox_note=sb.note,
    )
    return asset, cockpit


# ------------------------------------------------------------------ public
def run_analysis(inputs: AnalysisInputs, settings: Settings, *, source: str = "upload", label: str | None = None,
                 use_ml: bool = True) -> AnalysisRecord:
    """Run the model and build the dashboard views. Raises ValueError for bad input (shown to the user)."""
    eng = engine.require()
    sheet = _normalise_sheet(inputs.datasheet)
    with _LOCK:
        started = time.perf_counter()
        notes: list[str] = []
        tele = eng.inputs.to_minutes(inputs.telemetry, inputs.datasheet, "telemetry", notes)
        base = (eng.inputs.to_minutes(inputs.baseline, inputs.datasheet, "baseline", notes)
                if inputs.baseline is not None else None)
        pumps = set(sheet.index)
        context = _only_known_pumps(inputs.context, pumps, "context", notes)
        snapshots = _only_known_pumps(inputs.snapshots, pumps, "snapshots", notes)
        result = eng.predict(inputs.datasheet, tele, baseline=base, context=context,
                             snapshots=snapshots, use_ml=use_ml)

        alerts = [StoredAlert(**a) for a in result["alerts"]]
        if inputs.events is not None:
            _label_alerts(alerts, inputs.events)

        assets, cockpits = [], []
        for pump in result["pumps"]:
            minutes = tele[tele["asset_id"] == pump["asset_id"]]
            if minutes.empty:  # pump only present in the baseline file
                continue
            asset, cockpit = _pump_views(pump, minutes, sheet.loc[pump["asset_id"]], alerts, settings)
            assets.append(asset)
            cockpits.append(cockpit)
        elapsed = time.perf_counter() - started

    s = result["summary"]
    summary = AnalysisRunSummary(
        run_id=uuid.uuid4().hex,
        created_utc=_now_iso(),
        source=source,
        label=label,
        model_version=s["model_version"],
        physics_version=s.get("physics_version"),
        use_ml=use_ml,
        pumps=len(assets),
        alerts=len(alerts),
        ml_overrides=s["ml_overrides"],
        by_fault_type=s["by_fault_type"],
        data_start_utc=_iso(tele["window_start_utc"].min()),
        data_end_utc=_iso(tele["window_start_utc"].max() + pd.Timedelta(minutes=1)),
        processing_seconds=round(elapsed, 2),
        scored=inputs.events is not None,
        notes=_dedupe(notes + result["notes"]),
    )
    return AnalysisRecord(summary=summary, alerts=alerts, assets=assets, cockpits=cockpits)


def fleet_summary(record: AnalysisRecord | None) -> FleetSummary:
    assets = record.assets if record else []
    count = {sev: sum(1 for a in assets if a.severity == sev) for sev in PumpSeverity}
    healthy, total = count[PumpSeverity.OK], len(assets)
    sites = sorted({a.site for a in assets})
    run = record.summary if record else None
    return FleetSummary(
        vessel=(sites[0] if len(sites) == 1 else f"{len(sites)} sites · Fleet overview") if sites else "No data yet",
        watch=f"Model {run.model_version} · read-only" if run else "Upload data to run the model",
        critical=count[PumpSeverity.ACT_NOW],
        actionable=count[PumpSeverity.ACT_NOW] + count[PumpSeverity.ATTENTION],
        sensor_faults=count[PumpSeverity.SENSOR],
        availability_pct=round(100 * healthy / total, 1) if total else 0.0,
        healthy=healthy,
        total=total,
        nuisance_suppressed_pct=None,
        run_id=run.run_id if run else None,
        model_version=run.model_version if run else None,
        data_end_utc=run.data_end_utc if run else None,
    )


def alerts_csv(alerts: list[StoredAlert]) -> str:
    """the alerts in the organisers' template format (contract columns only)"""
    columns = ["asset_id", "alert_time_utc", "event_class", "fault_type", "confidence", "evidence",
               "recommended_action"]
    rows = [AlertPrediction.model_validate(a.model_dump()).model_dump(mode="json", include=set(columns))
            for a in alerts]
    return pd.DataFrame(rows, columns=columns).to_csv(index=False)
