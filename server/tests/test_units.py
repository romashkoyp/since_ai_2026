from __future__ import annotations

import pandas as pd

from src.analysis import _evidence_rows, _label_alerts, _only_known_pumps, _top_alert
from src.models import StoredAlert
from src.sandbox import PumpState, simulate

SHEET = pd.Series({"motor_rated_rpm": 1480.0, "pump_rated_flow_m3_h": 320.0, "npsh3_at_bep_m": 4.0,
                   "fluid": "water", "motor_rated_kw": 45.0, "control": "VFD_PRESSURE"})


def _alert(fault: str, t: str, cls: str = "MACHINE", conf: float = 0.8) -> StoredAlert:
    return StoredAlert(alert_id=f"{fault}-{t}", asset_id="P1", alert_time_utc=t, event_class=cls, fault_type=fault,
                       confidence=conf)


def test_evidence_parsing_reads_channel_z_scores():
    rows = _evidence_rows("vibration_rms_mm_s z=+44.3, flow_m3_h z=-17.3; 1x vibration x4.9 | ML agrees (0.80)")
    assert [(r.channel, r.sigma) for r in rows] == [("Vibration RMS", 44.3), ("Flow", -17.3)]
    assert [r.sigma for r in _evidence_rows("flow_m3_h deviates alone (z=-22.3)")] == [-22.3]
    assert _evidence_rows("missing rows") == []


def test_top_alert_prefers_severity_then_recency():
    bearing = _alert("BEARING_WEAR", "2026-01-01T10:00:00Z")
    cav_old = _alert("CAVITATION", "2026-01-01T08:00:00Z")
    cav_new = _alert("CAVITATION", "2026-01-01T09:00:00Z")
    assert _top_alert([bearing, cav_old, cav_new]) is cav_new
    assert _top_alert([]) is None


def test_ground_truth_labelling():
    hit = _alert("CAVITATION", "2026-01-01T12:00:00Z")
    wrong = _alert("BEARING_WEAR", "2026-01-01T13:00:00Z")
    false_alarm = _alert("IMBALANCE", "2026-01-05T00:00:00Z")
    events = pd.DataFrame([{"asset_id": "P1", "fault_type": "CAVITATION", "onset_utc": "2026-01-01T11:00:00Z",
                            "end_utc": "2026-01-01T20:00:00Z"}])
    _label_alerts([hit, wrong, false_alarm], events)
    assert (hit.true_fault_type, hit.correct) == ("CAVITATION", True)
    assert (wrong.true_fault_type, wrong.correct) == ("CAVITATION", False)
    assert (false_alarm.true_fault_type, false_alarm.correct) == ("NO_FAULT", False)


def test_extra_pumps_in_optional_files_are_dropped_with_a_note():
    notes: list[str] = []
    snaps = pd.DataFrame({"asset_id": ["P1", "P2", "P2"], "samples": [[0.0], [1.0], [2.0]]})
    kept = _only_known_pumps(snaps, {"P1"}, "snapshots", notes)
    assert list(kept["asset_id"]) == ["P1"]
    assert notes == ["snapshots: rows for pumps not in the datasheet were ignored (P2)"]
    assert _only_known_pumps(snaps, {"P9"}, "snapshots", []) is None
    assert _only_known_pumps(None, {"P1"}, "context", []) is None


def test_sandbox_affinity_laws():
    state = PumpState(speed_rpm=1480, flow_m3_h=300, suction_kpa=20, fluid_temp_c=30, power_kw=30)
    r = simulate(state, SHEET, "CAVITATION", 0.9, True, energy_price_eur_kwh=0.2, cooling_min_flow_fraction=0.8)
    assert r.npsh_at_88 > r.npsh_at_100              # less NPSH required at lower speed
    assert r.risk_at_88 < r.risk_at_100 == 0.9
    expected = (30 * 0.88 ** 3 - 30) * 24 * 0.2      # power ~ speed^3
    assert abs(r.energy_delta_eur_day - round(expected, 2)) < 1e-9
    assert r.cooling_margin_pct == 110               # 88 % of today's flow vs the 80 % the system needs


def test_sandbox_healthy_and_missing_sensors():
    nan = float("nan")
    state = PumpState(speed_rpm=nan, flow_m3_h=nan, suction_kpa=nan, fluid_temp_c=nan, power_kw=nan)
    r = simulate(state, SHEET.copy(), None, None, False, 0.15, 0.8)
    assert r.risk_at_100 == r.risk_at_88 == 0.05
    assert "no suction gauge" in r.note and "no flow meter" in r.note
