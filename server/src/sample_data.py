"""Sample fleet / cockpit / scorecard data for operator UI demo."""

from __future__ import annotations

from .models import (
    AlertPrediction,
    AssetStatus,
    CockpitResponse,
    EventClass,
    EvidenceRow,
    FaultType,
    FleetSummary,
    ScorecardResponse,
    TrendPoint,
    TrendSeries,
)

SAMPLE_ALERTS: list[AlertPrediction] = [
    AlertPrediction(
        asset_id="PUMP-04",
        alert_time_utc="2026-03-12T08:14:00Z",
        event_class=EventClass.MACHINE,
        fault_type=FaultType.BEARING_WEAR,
        confidence=0.91,
        evidence="bearing_temp_c residual + crest factor rise; BPFO harmonic elevated",
        recommended_action="Inspect DE bearing; plan replacement within 48h",
    ),
    AlertPrediction(
        asset_id="PUMP-06",
        alert_time_utc="2026-03-12T09:02:30Z",
        event_class=EventClass.MACHINE,
        fault_type=FaultType.SUCTION_STRAINER_CLOGGING,
        confidence=0.87,
        evidence="suction_pressure_kpa drop with stable discharge; flow shortfall",
        recommended_action="Clean suction strainer; verify NPSH margin",
    ),
    AlertPrediction(
        asset_id="PUMP-02",
        alert_time_utc="2026-03-12T07:41:00Z",
        event_class=EventClass.SENSOR,
        fault_type=FaultType.SENSOR_DRIFT,
        confidence=0.78,
        evidence="vibration_rms_mm_s slow slope vs coupled channels stable",
        recommended_action="Calibrate vibration sensor; mask channel for machine checks",
    ),
    AlertPrediction(
        asset_id="PUMP-08",
        alert_time_utc="2026-03-12T10:05:00Z",
        event_class=EventClass.MACHINE,
        fault_type=FaultType.CAVITATION,
        confidence=0.89,
        evidence="suction pressure -3.8σ; 2.6–3.0 kHz cavitation band rising",
        recommended_action="Derate to 88% speed; clean strainer before port arrival",
    ),
    AlertPrediction(
        asset_id="PUMP-11",
        alert_time_utc="2026-03-12T10:18:00Z",
        event_class=EventClass.MACHINE,
        fault_type=FaultType.CAVITATION,
        confidence=0.84,
        evidence="high-frequency accel RMS spike with suction head drop",
        recommended_action="Reduce speed setpoint; check suction level",
    ),
]

SAMPLE_ASSETS: list[AssetStatus] = [
    AssetStatus(asset_id="PUMP-01", site="M/V Borealis", system="SW cooling", tier="T1", status="healthy", mode="RUNNING", load_pct=74, open_alerts=0),
    AssetStatus(asset_id="PUMP-02", site="M/V Borealis", system="SW cooling", tier="T1", status="sensor_issue", mode="RUNNING", load_pct=71, open_alerts=1, fault_summary="Sensor drift on vib channel"),
    AssetStatus(asset_id="PUMP-03", site="M/V Borealis", system="LT freshwater", tier="T0", status="healthy", mode="STANDBY", load_pct=0, open_alerts=0),
    AssetStatus(asset_id="PUMP-04", site="M/V Borealis", system="LT freshwater", tier="T2", status="alert", mode="RUNNING", load_pct=82, open_alerts=1, fault_summary="Bearing BPFO rising", rul_hours=68),
    AssetStatus(asset_id="PUMP-05", site="Plant B", system="CW loop", tier="T1", status="healthy", mode="RUNNING", load_pct=66, open_alerts=0),
    AssetStatus(asset_id="PUMP-06", site="Plant B", system="CW loop", tier="T1", status="alert", mode="RUNNING", load_pct=79, open_alerts=1, fault_summary="Suction strainer clogging", rul_hours=24),
    AssetStatus(asset_id="PUMP-07", site="Plant B", system="Transfer", tier="T0", status="healthy", mode="STOPPED", load_pct=0, open_alerts=0),
    AssetStatus(asset_id="PUMP-08", site="Vessel C", system="LT main", tier="T2", status="alert", mode="RUNNING", load_pct=88, open_alerts=1, fault_summary="Strainer / cavitation risk", rul_hours=24),
    AssetStatus(asset_id="PUMP-09", site="Vessel C", system="LT main", tier="T1", status="healthy", mode="STANDBY", load_pct=0, open_alerts=0),
    AssetStatus(asset_id="PUMP-10", site="Vessel C", system="SW cooling", tier="T1", status="healthy", mode="RUNNING", load_pct=58, open_alerts=0),
    AssetStatus(asset_id="PUMP-11", site="Vessel C", system="SW cooling", tier="T2", status="alert", mode="RUNNING", load_pct=84, open_alerts=1, fault_summary="Cavitation signature", rul_hours=36),
    AssetStatus(asset_id="PUMP-12", site="Vessel C", system="Transfer", tier="T0", status="healthy", mode="STANDBY", load_pct=0, open_alerts=0),
]


def fleet_summary() -> FleetSummary:
    total = len(SAMPLE_ASSETS)
    healthy = sum(1 for a in SAMPLE_ASSETS if a.status == "healthy")
    actionable = sum(1 for a in SAMPLE_ASSETS if a.status == "alert")
    sensor = sum(1 for a in SAMPLE_ASSETS if a.status == "sensor_issue")
    return FleetSummary(
        vessel="M/V Borealis Voyager · Fleet overview",
        watch="Operator triage · read-only",
        critical=0,
        actionable=actionable,
        sensor_faults=sensor,
        availability_pct=round(100 * healthy / total, 1),
        healthy=healthy,
        total=total,
        nuisance_suppressed_pct=62.0,
    )


def _series(name: str, unit: str, values: list[float], threshold: float | None = None) -> TrendSeries:
    points = [TrendPoint(t=f"t-{len(values) - i}", value=v) for i, v in enumerate(values)]
    return TrendSeries(name=name, unit=unit, points=points, threshold=threshold)


COCKPITS: dict[str, CockpitResponse] = {
    "PUMP-08": CockpitResponse(
        asset_id="PUMP-08",
        title="LT Main Cooling Pump",
        diagnosis="Suction strainer clogging / early cavitation",
        event_class=EventClass.MACHINE,
        confidence=0.89,
        safe_window="~24h at 88% speed · port ETA 18h",
        evidence=[
            EvidenceRow(channel="Suction pressure", sigma=-3.8, note="Below healthy envelope"),
            EvidenceRow(channel="Acoustic resonance", sigma=4.3, note="2.6–3.0 kHz band"),
            EvidenceRow(channel="Head vs affinity", sigma=-2.9, note="Curve left of BEP"),
        ],
        sop=[
            "Derate VFD to 88% immediately",
            "Confirm standby pump ready",
            "Schedule strainer clean at next port",
            "Do not write setpoints from this UI (read-only)",
        ],
        trends=[
            _series("Discharge head", "m", [42, 41, 40, 39, 38, 37, 36.5, 36], 40),
            _series("Suction pressure", "kPa", [48, 46, 44, 41, 38, 35, 33, 31], 40),
            _series("Motor power", "kW", [52, 53, 54, 55, 56, 57, 58, 59], 60),
        ],
        sandbox_default_speed_pct=88,
        npsh_at_100=0.38,
        npsh_at_88=1.84,
        risk_at_100=0.78,
        risk_at_88=0.14,
        energy_delta_eur_day=-34.2,
        cooling_margin_pct=106,
    ),
    "PUMP-04": CockpitResponse(
        asset_id="PUMP-04",
        title="LT Freshwater Pump",
        diagnosis="Drive-end bearing wear (BPFO)",
        event_class=EventClass.MACHINE,
        confidence=0.91,
        safe_window="~68h remaining · schedule change-out",
        evidence=[
            EvidenceRow(channel="Bearing temp", sigma=3.1, note="Rising residual"),
            EvidenceRow(channel="Crest factor", sigma=2.8, note="Impactivity up"),
            EvidenceRow(channel="BPFO band", sigma=4.1, note="142.8 Hz elevated"),
        ],
        sop=[
            "Keep load under 85%",
            "Confirm lubrication state",
            "Order DE bearing kit",
            "Plan swap within 48h",
        ],
        trends=[
            _series("Bearing temp", "°C", [58, 59, 61, 63, 65, 67, 69, 71], 70),
            _series("Vibration RMS", "mm/s", [2.1, 2.2, 2.4, 2.6, 2.9, 3.1, 3.4, 3.6], 3.2),
            _series("Motor current", "A", [88, 89, 89, 90, 91, 91, 92, 93], 95),
        ],
        sandbox_default_speed_pct=90,
        npsh_at_100=1.9,
        npsh_at_88=2.2,
        risk_at_100=0.62,
        risk_at_88=0.28,
        energy_delta_eur_day=-12.0,
        cooling_margin_pct=118,
    ),
}

SCORECARD = ScorecardResponse(
    composite_score=87.7,
    event_f1=0.94,
    precision=1.0,
    fault_type_recall=0.778,
    timeliness=0.91,
    false_alarms=0,
    t0_vs_t1=[
        {"capability": "Cavitation detection", "t0": "No", "t1": "Yes"},
        {"capability": "Impeller wear", "t0": "No", "t1": "Yes"},
        {"capability": "Sensor drift isolation", "t0": "No", "t1": "Yes"},
        {"capability": "Bearing faults (FFT)", "t0": "No", "t1": "Yes"},
        {"capability": "Shaft misalignment", "t0": "No", "t1": "Yes"},
        {"capability": "Warning lead time", "t0": "26 h", "t1": "168 h"},
    ],
    hardware_bom=[
        {"item": "Magnetic tri-axial MEMS accelerometer", "eur": 180},
        {"item": "Split-core CT clamp", "eur": 65},
        {"item": "DIN-rail edge IPC", "eur": 205},
    ],
    economics=[
        {"metric": "8-pump critical kit", "value": "€3,600"},
        {"metric": "12-pump full fleet", "value": "€5,400"},
        {"metric": "Crew install time", "value": "45 min / pump"},
        {"metric": "Single avoided ME casualty", "value": "€48,500"},
        {"metric": "Net payback", "value": "< 1 avoided event"},
    ],
)
