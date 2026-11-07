"""Sample fleet alerts for local / demo wiring. Replace with retrofit predictions later."""

from __future__ import annotations

from .models import AlertPrediction, AssetStatus, EventClass, FaultType

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
    AssetStatus(asset_id="PUMP-01", site="Vessel A", tier="T0", status="healthy", open_alerts=0),
    AssetStatus(asset_id="PUMP-02", site="Vessel A", tier="T1", status="sensor_issue", open_alerts=1),
    AssetStatus(asset_id="PUMP-04", site="Plant B", tier="T2", status="alert", open_alerts=1),
    AssetStatus(asset_id="PUMP-06", site="Plant B", tier="T1", status="alert", open_alerts=1),
    AssetStatus(asset_id="PUMP-11", site="Vessel C", tier="T2", status="alert", open_alerts=1),
    AssetStatus(asset_id="PUMP-12", site="Vessel C", tier="T0", status="healthy", open_alerts=0),
]
