"""Static retrofit business case for the scorecard screen (not a model output)."""

from __future__ import annotations

from .models import ScorecardResponse

SCORECARD = ScorecardResponse(
    composite_score=95.8,
    event_f1=1.0,
    precision=1.0,
    fault_type_recall=0.889,
    timeliness=0.928,
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
