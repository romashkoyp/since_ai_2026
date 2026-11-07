"""What-if speed derate for the cockpit's mitigation simulator (read-only: nothing is ever written to a PLC).

Physics: pump affinity laws on the pump's latest steady readings and its datasheet.
    speed ratio s (1.0 = today's speed):  flow ~ s,  head ~ s^2,  power ~ s^3,  NPSH required ~ s^2
Cooling: today's flow is assumed to meet today's heat load; the cooled system tolerates down to
`cooling_min_flow_fraction` of it (setting COOLING_MIN_FLOW_FRACTION).
NPSH available uses the same vapour-pressure model as the detector (Antoine equation for water).
Risk is NOT a failure-probability model: it is the model's confidence that the fault is present, scaled by how
strongly the fault's driver depends on speed. The cockpit shows this assumption as `sandbox_note`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

G = 9.81
DERATE = 0.88  # the UI slider interpolates between 100 % and this speed
ATM_KPA = 101.3
DEFAULT_STATIC_HEAD_M = 2.5  # same assumption the detector uses when a pump has no suction gauge

_SUCTION_DRIVEN = {"CAVITATION", "AIR_ENTRAINMENT", "SUCTION_STRAINER_CLOGGING"}
_DYNAMIC_LOAD = {"BEARING_WEAR", "MISALIGNMENT", "IMBALANCE"}
HEALTHY_RISK = 0.05


@dataclass(frozen=True)
class PumpState:
    """Median of the last steady running hour (NaN when the pump has no such sensor)."""

    speed_rpm: float
    flow_m3_h: float
    suction_kpa: float
    fluid_temp_c: float
    power_kw: float


@dataclass(frozen=True)
class SandboxResult:
    npsh_at_100: float
    npsh_at_88: float
    risk_at_100: float
    risk_at_88: float
    energy_delta_eur_day: float
    cooling_margin_pct: float
    cooling_safe_flow_m3h: float
    note: str


def _rho(fluid: str) -> float:
    f = str(fluid).lower()
    return 1004.0 if "sea" in f else (975.0 if "hot" in f else 1000.0)


def _vapour_kpa(temp_c: float) -> float:
    t = 25.0 if math.isnan(temp_c) else temp_c
    return 10 ** (8.07131 - 1730.63 / (233.426 + t)) * 0.133322


def latest_state(minutes: pd.DataFrame) -> PumpState:
    """Median of the last 60 steady running minutes (falls back to the last 60 minutes of any data)."""
    run = minutes[minutes["operating_mode"] == "RUNNING"] if "operating_mode" in minutes else minutes
    window = (run if len(run) else minutes).tail(60)

    def med(channel: str) -> float:
        col = f"{channel}__mean"
        return float(window[col].median()) if col in window and window[col].notna().any() else float("nan")

    return PumpState(
        speed_rpm=med("motor_speed_rpm"),
        flow_m3_h=med("flow_m3_h"),
        suction_kpa=med("suction_pressure_kpa"),
        fluid_temp_c=med("fluid_temp_c"),
        power_kw=med("motor_power_kw"),
    )


def simulate(state: PumpState, sheet: pd.Series, fault_type: str | None, confidence: float | None,
             is_machine_fault: bool, energy_price_eur_kwh: float, cooling_min_flow_fraction: float) -> SandboxResult:
    rated_rpm = float(sheet["motor_rated_rpm"])
    rated_flow = float(sheet["pump_rated_flow_m3_h"])
    npsh3 = float(sheet["npsh3_at_bep_m"])
    rho = _rho(sheet.get("fluid", ""))
    assumptions: list[str] = []

    r = state.speed_rpm / rated_rpm if not math.isnan(state.speed_rpm) and rated_rpm > 0 else 1.0
    r = float(np.clip(r, 0.3, 1.2))
    if not math.isnan(state.flow_m3_h):
        flow_now = state.flow_m3_h
        q = float(np.clip(flow_now / (r * rated_flow), 0.0, 1.6))
    else:
        flow_now, q = rated_flow * r, 1.0
        assumptions.append("no flow meter: flow estimated from speed")
    if not math.isnan(state.suction_kpa):
        suction = state.suction_kpa
    else:
        suction = rho * G * DEFAULT_STATIC_HEAD_M / 1000
        assumptions.append(f"no suction gauge: {DEFAULT_STATIC_HEAD_M} m static suction head assumed")

    def npsh_margin(s: float) -> tuple[float, float]:
        """(NPSHa - NPSHr in metres, NPSHa / NPSHr) at speed ratio s"""
        v = 2.5 * q * r * s  # suction line sized for 2.5 m/s at BEP
        npsha = (suction + ATM_KPA - _vapour_kpa(state.fluid_temp_c)) * 1000 / (rho * G) + v * v / (2 * G)
        npshr = npsh3 * (r * s) ** 2 * (0.55 + 0.45 * q ** 2.6)
        return npsha - npshr, npsha / npshr

    m100, sigma100 = npsh_margin(1.0)
    m88, sigma88 = npsh_margin(DERATE)

    if math.isnan(state.power_kw):
        rated_kw = float(sheet.get("motor_rated_kw") or 0) or 0.0
        power_now = rated_kw * r ** 3
        if rated_kw:
            assumptions.append("no power meter: power estimated from rated kW")
    else:
        power_now = state.power_kw
    energy_delta = (power_now * DERATE ** 3 - power_now) * 24 * energy_price_eur_kwh

    # The cooled system needs `cooling_min_flow_fraction` of today's flow (today's flow meets today's heat load).
    safe_flow = cooling_min_flow_fraction * flow_now
    cooling = 100 * flow_now * DERATE / safe_flow if safe_flow > 0 else 0.0
    control = str(sheet.get("control", "")).upper()
    if control in ("FIXED_SPEED", "FLOW_VALVE"):
        assumptions.append("this pump has no speed drive, so the derate shows what a VFD retrofit would allow")
    min_ratio = sheet.get("min_speed_ratio")
    if min_ratio is not None and not pd.isna(min_ratio) and r * DERATE < float(min_ratio):
        assumptions.append(f"{round(DERATE * 100)}% of today's speed is below the drive minimum "
                           f"({float(min_ratio):.0%} of rated)")

    risk100 = float(confidence) if (is_machine_fault and confidence is not None) else HEALTHY_RISK
    if not is_machine_fault:
        risk88 = risk100
    elif fault_type in _SUCTION_DRIVEN:
        risk88 = risk100 * min(1.0, sigma100 / sigma88)
    elif fault_type in _DYNAMIC_LOAD:
        risk88 = risk100 * DERATE ** 2
    else:
        risk88 = risk100 * DERATE

    note = ("Affinity-law estimate from the last running hour. Risk = model confidence the fault is present, "
            "scaled by how strongly it depends on speed; it is a guide, not a failure probability. "
            f"Cooling margin = flow at {round(DERATE * 100)}% speed vs the {round(cooling_min_flow_fraction * 100)}% "
            "of today's flow the cooled system needs.")
    if assumptions:
        note += " Assumed: " + "; ".join(assumptions) + "."

    return SandboxResult(
        npsh_at_100=round(m100, 2), npsh_at_88=round(m88, 2),
        risk_at_100=round(float(np.clip(risk100, 0, 1)), 3), risk_at_88=round(float(np.clip(risk88, 0, 1)), 3),
        energy_delta_eur_day=round(energy_delta, 2), cooling_margin_pct=round(cooling),
        cooling_safe_flow_m3h=round(safe_flow, 1), note=note,
    )
