# SENTRY module: physics residuals & NPSH margin, reusing the simulator's own equations (vectorized).
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from retrofit_sim import physics as ph  # noqa: E402


def fluid_density(fluid: str, t_c):
    t = np.asarray(t_c, dtype=float)
    if "sea" in fluid.lower() or "brackish" in fluid.lower():
        return ph.water_density(t, salinity_psu=6.0)
    return ph.water_density(t)


class PumpCurve:
    """Per-asset curve wrapper built from assets.csv constants. Vectorized (arrays in / arrays out)."""

    def __init__(self, a):
        self.q_bep = float(a.pump_rated_flow_m3_h)          # m3/h
        self.h_bep = float(a.pump_rated_head_m)
        self.h0 = float(a.pump_shutoff_head_m) / self.h_bep
        self.eta_bep = float(a.pump_bep_efficiency)
        self.npsh3_bep = float(a.npsh3_at_bep_m)
        self.rated_rpm = float(a.motor_rated_rpm)
        self.static_head = float(a.static_head_m)
        self.fluid = str(a.fluid)

    def Q_from_head(self, H_m, r, fH=1.0):
        """Invert H = Hb(h0 r^2 - (h0-1)(Q/Qb)^2) fH  ->  Q [m3/h]. Arrays."""
        H_m = np.asarray(H_m, dtype=float)
        r = np.asarray(r, dtype=float)
        fH = np.maximum(np.asarray(fH, dtype=float), 1e-6)
        inner = (self.h0 * r ** 2 - H_m / (fH * self.h_bep)) / (self.h0 - 1.0)
        return np.clip(np.sqrt(np.maximum(inner, 0.0)), 0.0, 2.0) * self.q_bep

    def npshr(self, Q_m3h, r):
        q = np.clip(np.asarray(Q_m3h, dtype=float) / np.maximum(np.asarray(r, dtype=float) * self.q_bep, 1e-3), 0.0, 2.0)
        rr = np.maximum(np.asarray(r, dtype=float), 1e-6)
        return np.asarray(self.npsh3_bep, dtype=float) * rr ** 2 * (0.55 + 0.45 * q ** 2.6)

    def npsh_margin(self, suction_kpa_gauge, t_fluid_c, Q_m3h, r):
        """sigma = NPSHa / NPSH3 [m] from suction gauge pressure. Arrays. NaN-consistent."""
        suc = np.asarray(suction_kpa_gauge, dtype=float)
        t = np.asarray(t_fluid_c, dtype=float)
        r = np.maximum(np.asarray(r, dtype=float), 0.05)
        rho = fluid_density(self.fluid, t)
        suction_abs = suc * 1e3 + ph.P_ATM
        vmin = 0.2
        rr = np.maximum(r, 0.3)
        v = np.maximum(2.5 * np.asarray(Q_m3h, dtype=float) / (rr * self.q_bep), vmin)
        npsha_m = suction_abs / (rho * ph.G) + v ** 2 / (2 * ph.G)
        npsha_m -= ph.vapour_pressure_pa(t) / (rho * ph.G)
        return npsha_m / np.maximum(self.npshr(Q_m3h, r), 0.1)
