# SENTRY module: detection engine + alert manager (final implementation).
# Causal, per-asset, minute-resolution. Thresholds calibrated against the measured
# traces (analysis/08_out*.txt, deep-dive report) and the scorer's rules
# (BENCHMARK_RULES 4: window opens at max(onset, detectable - 6 h); bursts merge < 5 min).
import numpy as np
import pandas as pd

from .regime import build_residuals, rolling_noise_ratio, frozen_range_units
from .physics import PumpCurve

# ---- calibrated thresholds ----
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "src"))
from retrofit_sim import physics as _ph


def ph_water_density(fluid, t_c):
    if "sea" in fluid.lower() or "brackish" in fluid.lower():
        return _ph.water_density(t_c, salinity_psu=6.0)
    return _ph.water_density(t_c)


SIGMA_EVENT = 1.15        # NPSH margin < 1.15 for >= 5 min = the label's cavitation episode
SIGMA_REARM = 1.30
SUC_DEV_KPA = -2.2        # clog on VFD assets: suction below expanding 48 h regime median
PERSIST_CLOG = 120
PERSIST_SUC = 30          # fixed-speed clog: z(suction) < -4 sustained
Z_SUC_FS = -4.0
PERSIST_FAST = 5          # restriction: fast-coupled hydraulic step
Z_RESTR_FLOW = -3.0
Z_DIS_UP = 2.0
Z_SPEED_SAG = -2.0
Z_ACCEL_OFFBEP = 3.0
Z_DIS_DOWN = -3.0         # air: discharge/flow/power collapse without NPSH break
Z_POWER_DOWN = -3.0
PERSIST_AIR = 15
Z_T0_RESTR_DIS = 3.5
Z_T0_RESTR_CUR = -2.0
Z_STEP = 3.5              # calibration shift: level step > 3.5 MAD with covariates flat
PERSIST_STEP = 45
DRIFT_DEV = 1.0           # drift: 2-h median vs 12-h trailing median dev in MAD units
DRIFT_MONO = 0.62
STUCK_FRAC = 0.05         # 60-min range < 30 % of noise = frozen transmitter
PERSIST_STUCK = 30
NOISE_RATIO = 3.0         # per-minute std > 3x noise floor, sustained 15 min
SPIKE_Z = 6.0
Z_CREST = 2.6             # crest jump with hydraulics flat -> bearing
PERSIST_CREST = 40
Z_VEL_UMB = 3.5           # velocity elevation; snapshot types imbalance vs misalignment
PERSIST_VEL = 45
VEL_HOLD_SNAP = 2880       # hold a pending vibration-domain alert for the next snapshot
SNAP_MIS_D2 = 7.0         # s2x >= baseline + 7 dB
SNAP_MIS_D1 = 4.0
SNAP_IMB_D1 = 6.0
SNAP_BEARING = 15.0       # BPFO envelope SNR on 2 consecutive snapshots
REMINDER_H = 12

VIB_FAMILY = {"vibration_rms_mm_s", "vibration_accel_rms_g", "vibration_crest_factor"}
STEP_EXCL = VIB_FAMILY | {"motor_speed_rpm", "fluid_temp_c", "motor_winding_temp_c"}
DRIFT_EXCL = VIB_FAMILY | {"motor_speed_rpm", "fluid_temp_c", "ambient_temp_c",
                              "flow_m3_h", "motor_power_kw", "discharge_pressure_kpa", "motor_winding_temp_c"}
STUCK_EXCL = VIB_FAMILY | {"motor_speed_rpm"}
NOISE_EXCL = VIB_FAMILY | {"motor_speed_rpm"}
           # one free reminder per 12 h (scorer)
GRACE_MIN = 3
COMM_GAP_MIN = 30


def _sus(mask, n):
    s = pd.Series(np.nan_to_num(np.asarray(pd.Series(mask).astype(float)), nan=0.0))
    return (s.rolling(n, min_periods=n).sum().values >= n - 0.01) & np.asarray(pd.Series(mask).fillna(False), dtype=bool)


class AssetSentry:
    """Causal streaming detection for one asset."""

    ACTIONS = {
        "SUCTION_STRAINER_CLOGGING": "Inspect and clean the suction strainer; verify strainer dP before restart.",
        "CAVITATION": "Reduce speed until NPSH margin recovers; inspect sea chest, strainer and suction level.",
        "DISCHARGE_RESTRICTION": "Check discharge valve position and heat-exchanger dP/dT; look for partial closure after work.",
        "AIR_ENTRAINMENT": "Check suction submergence / basin level and sea-chest aeration.",
        "BEARING_WEAR": "Plan a bearing replacement; capture a vibration route in the meantime.",
        "IMBALANCE": "Inspect impeller deposits; balance after next clean; watch the 1x trend.",
        "MISALIGNMENT": "Check coupling alignment (especially after recent work); watch the 2x trend.",
        "IMPELLER_WEAR": "Verify against the pump curve; plan impeller/wear-ring overhaul.",
        "SENSOR_DRIFT": "Check transmitter zero/span; compare with coupled gauges before machine work.",
        "SENSOR_STUCK": "Inspect the transmitter for a frozen value; compare with coupled gauges.",
        "SENSOR_CALIBRATION_SHIFT": "Recalibrate the transmitter against a reference; compare with coupled gauges.",
        "SENSOR_NOISE_SPIKES": "Check transmitter wiring/shielding/terminations.",
        "COMMUNICATION_LOSS": "Check the fieldbus/gateway segment; monitoring is blind until restored.",
        "UNKNOWN": "Review the listed evidence channels; cause not yet clear - inspect before acting.",
    }
    COVARIATE = {
        "suction_pressure_kpa": ["flow_m3_h", "discharge_pressure_kpa", "motor_speed_rpm", "motor_power_kw"],
        "discharge_pressure_kpa": ["flow_m3_h", "motor_current_a", "motor_speed_rpm", "motor_power_kw"],
        "flow_m3_h": ["motor_current_a", "discharge_pressure_kpa", "suction_pressure_kpa"],
        "motor_current_a": ["motor_power_kw", "motor_speed_rpm", "flow_m3_h"],
        "motor_power_kw": ["motor_current_a", "motor_speed_rpm", "flow_m3_h"],
        "bearing_temp_c": ["vibration_accel_rms_g", "vibration_rms_mm_s"],
        "motor_winding_temp_c": ["motor_current_a", "motor_power_kw"],
        "vibration_rms_mm_s": ["motor_power_kw", "motor_current_a"],
        "vibration_accel_rms_g": ["bearing_temp_c"],
        "vibration_crest_factor": ["vibration_accel_rms_g"],
        "fluid_temp_c": ["ambient_temp_c", "motor_current_a"],
    }

    def __init__(self, asset_row, feats, context, snap_df=None, ffill_sparse=90):
        self.a = asset_row
        self.feats = feats.sort_index()
        self.channels = [c[:-6] for c in self.feats.columns if c.endswith("__mean")]
        self.res = build_residuals(self.feats, self.channels, asset_row, ffill_sparse=ffill_sparse)
        self.curve = PumpCurve(asset_row)
        self.n = len(self.feats)
        self.t = self.feats.index
        self.ctx = None
        if context is not None and len(context):
            ctx = context.copy()
            ctx["timestamp_utc"] = pd.to_datetime(ctx["timestamp_utc"])
            self.ctx = ctx.set_index("timestamp_utc")[["sea_state_hs_m"]].reindex(self.feats.index).ffill(limit=60)
        self.runmask = (
            (self.feats["operating_mode"] == "RUNNING")
            & (self.feats["running_fraction"] > 0.9)
            & (self.feats["rows"] >= 55)
        ).values
        self.run60 = pd.Series(self.runmask.astype(float)).rolling(60, min_periods=10).mean().values >= 0.8
        self.snap_df = snap_df if (snap_df is not None and len(snap_df)) else None
        self.snap_metrics = None
        self._line_base = None
        self._snap_cursor = 0
        self.bpfo_hist = []
        self.latch = {}
        self.alerts = []
        self.pending_vel = None
        self.last_machine_fire = None

    # ---------------- basics ----------------
    def z(self, c):
        col = f"{c}__z"
        return self.res[col].values if col in self.res.columns else np.full(self.n, np.nan)

    def lvl(self, c):
        col = f"{c}__lvl"
        return self.res[col].values if col in self.res.columns else np.full(self.n, np.nan)

    def has(self, c):
        return f"{c}__mean" in self.feats.columns and self.feats[f"{c}__mean"].notna().sum() > 100

    def pct(self, c, i):
        if f"{c}__mean" not in self.feats.columns:
            return np.nan
        x = self.feats[f"{c}__mean"].values[i]
        m = self.lvl(c)[i]
        if np.isfinite(x) and np.isfinite(m) and abs(m) > 1e-9:
            return 100.0 * (x - m) / abs(m)
        return np.nan

    def fire(self, fault, pos, evidence, event_class=None, conf=0.6, alert_time=None):
        t = alert_time if alert_time is not None else self.t[pos]
        st = self.latch.get(fault)
        if st is not None:
            if (t - st["first"]).total_seconds() < REMINDER_H * 3600 or len(st["rems"]) >= 1:
                return False
            st["rems"].append(t)
        else:
            self.latch[fault] = {"first": t, "rems": []}
        cls = event_class or ("SENSOR" if fault.startswith("SENSOR") or fault == "COMMUNICATION_LOSS" else "MACHINE")
        if cls == "MACHINE" and fault != "CAVITATION" and self.last_machine_fire is not None \
                and (t - self.last_machine_fire).total_seconds() < 75 * 60:
            return False
        if cls == "MACHINE":
            self.last_machine_fire = t
        self.alerts.append({
            "asset_id": self.a.asset_id,
            "alert_time_utc": t,
            "event_class": cls,
            "fault_type": fault,
            "confidence": round(float(np.clip(conf, 0.5, 0.97)), 2),
            "evidence": str(evidence)[:240],
            "recommended_action": self.ACTIONS.get(fault, self.ACTIONS["UNKNOWN"]),
        })
        return True

    def _not_clog_trend(self, c):
        if c != "suction_pressure_kpa" or not self.has("suction_pressure_kpa"):
            return np.ones(self.n, dtype=bool)
        suc = self.feats["suction_pressure_kpa__mean"].values.astype(float)
        xv = np.where(self.runmask, suc, np.nan)
        s = pd.Series(xv, index=self.t)
        dev = (s.rolling(120, min_periods=30).median() - s.rolling(2880, min_periods=480).median()).values
        return ~np.nan_to_num(-dev > 1.8)

    def _ev(self, cnames, i, extra="", signs=None):
        segs = []
        for c in cnames:
            p = self.pct(c, i)
            if np.isfinite(p) and abs(p) >= 0.5:
                segs.append(f"{c.split('_')[1] if len(c.split('_')) > 1 else c} {p:+.0f}%")
        if extra:
            segs.append(extra)
        return "; ".join(segs)[:240]

    # ---------------- NPSH margin ----------------
    def compute_sigma(self):
        if not self.has("suction_pressure_kpa"):
            return None
        suc_g = self.feats["suction_pressure_kpa__mean"].values.astype(float)
        tf = (self.feats["fluid_temp_c__mean"].values.astype(float)
              if self.has("fluid_temp_c") else np.full(self.n, 20.0))
        dis_g = (self.feats["discharge_pressure_kpa__mean"].values.astype(float)
                 if self.has("discharge_pressure_kpa") else np.full(self.n, np.nan))
        r = (np.clip(self.feats["motor_speed_rpm__mean"].values.astype(float) / self.curve.rated_rpm, 0.3, 1.2)
             if self.has("motor_speed_rpm") else np.ones(self.n))
        if self.has("flow_m3_h"):
            Q = self.feats["flow_m3_h__mean"].values.astype(float)
        else:
            H = (dis_g - suc_g) * 1e3 / (995.0 * 9.80665)
            Q = self.curve.Q_from_head(np.nan_to_num(H, nan=20.0), r)
        hs = np.nan_to_num(self.ctx["sea_state_hs_m"].values, nan=0.0) if self.ctx is not None else np.zeros(self.n)
        suc_sm = pd.Series(suc_g).rolling(10, min_periods=3).median().values
        suc_use = np.where(hs >= 2.5, suc_sm, suc_g)
        with np.errstate(all="ignore"):
            sig = self.curve.npsh_margin(suc_use, np.clip(tf, 0.0, 120.0),
                                         np.clip(Q, 0.1, 3.0 * self.curve.q_bep), r)
        sig[~self.runmask] = np.nan
        return sig

    # ---------------- snapshot analyzer ----------------
    def prep_snapshots(self):
        if self.snap_df is None:
            self.snap_metrics = None
            return
        from . import snapshots as sn
        met = sn.snapshot_metrics(self.snap_df, float(self.a.bearing_bpfo_order),
                                  float(self.a.bearing_bpfi_order), int(self.a.impeller_vanes))
        met = met.sort_values("timestamp_utc").reset_index(drop=True)
        self.snap_metrics = met
        first = met.head(6)
        self._line_base = {"s1x": float(first["s1x"].median()), "s2x": float(first["s2x"].median())}

    def handle_snapshot(self, row, pos, gt):
        bp = float(row.get("e_bpfo_snr", np.nan))
        s1 = float(row.get("s1x", np.nan))
        s2 = float(row.get("s2x", np.nan))
        self.bpfo_hist.append(bp)
        base = self._line_base if self._line_base else {"s1x": np.nan, "s2x": np.nan}
        extra = f"BPFO SNR {bp:.0f} dB, rel-baseline 1x {s1 - base['s1x']:+.0f} dB, 2x {s2 - base['s2x']:+.0f} dB"
        h = [v for v in self.bpfo_hist if np.isfinite(v)]
        if len(h) >= 2 and h[-1] >= SNAP_BEARING and h[-2] >= SNAP_BEARING:
            self.pending_vel = None
            conf = 0.85 if h[-1] > 25.0 else 0.7
            self.fire("BEARING_WEAR", pos, self._ev(["vibration_accel_rms_g"], pos, extra=extra),
                      conf=conf, alert_time=gt)
            return
        if np.isfinite(s2) and np.isfinite(base["s2x"]) and s2 >= base["s2x"] + SNAP_MIS_D2 \
                and np.isfinite(s1) and s1 >= base["s1x"] + SNAP_MIS_D1:
            self.pending_vel = None
            self.fire("MISALIGNMENT", pos, self._ev(["vibration_rms_mm_s"], pos, extra=extra),
                      conf=0.75, alert_time=gt)
            return
        if np.isfinite(s1) and np.isfinite(base["s1x"]) and s1 >= base["s1x"] + SNAP_IMB_D1 \
                and (not np.isfinite(bp) or bp < 12.0):
            self.pending_vel = None
            self.fire("IMBALANCE", pos, self._ev(["vibration_rms_mm_s"], pos, extra=extra),
                      conf=0.7, alert_time=gt)
            return
        if self.pending_vel is not None:
            j, conf = self.pending_vel
            if (gt - self.t[j]).total_seconds() > VEL_HOLD_SNAP * 60:
                self.fire("UNKNOWN", pos, self._ev(["vibration_rms_mm_s"], pos,
                          extra="vibration elevated, spectrum shows no specific line"),
                          event_class="MACHINE", conf=conf, alert_time=gt)
                self.pending_vel = None

    # ---------------- precomputed flags ----------------
    def _precompute(self):
        n = self.n
        F = {}
        if all(self.has(c) for c in ("flow_m3_h", "discharge_pressure_kpa", "motor_power_kw")):
            trio = (self.z("flow_m3_h") < Z_RESTR_FLOW) & (self.z("discharge_pressure_kpa") < Z_DIS_DOWN) \
                & (self.z("motor_power_kw") < Z_POWER_DOWN)
            F["air"] = _sus(trio, PERSIST_AIR) & self.runmask
        if self.has("discharge_pressure_kpa") and self.has("motor_power_kw"):
            unk = (np.abs(np.nan_to_num(self.z("motor_power_kw"))) > 2.5) \
                & (np.abs(np.nan_to_num(self.z("discharge_pressure_kpa"))) > 2.5)
            F["unkhyd"] = _sus(unk, PERSIST_FAST * 12) & self.runmask
        if self.has("suction_pressure_kpa"):
            suc = self.z("suction_pressure_kpa")
            dis_ok = (self.z("discharge_pressure_kpa") > Z_DIS_DOWN) if self.has("discharge_pressure_kpa") else True
            F["clogfs"] = _sus((suc < Z_SUC_FS) & np.asarray(dis_ok, dtype=bool), PERSIST_SUC) & self.runmask
        if self.has("suction_pressure_kpa") and (self.has("motor_speed_rpm") or "VFD" in str(self.a.control).upper()):
            suc = self.feats["suction_pressure_kpa__mean"].values.astype(float)
            xv = np.where(self.runmask, suc, np.nan)
            s = pd.Series(xv, index=self.t)
            base48 = s.rolling(2880, min_periods=480).median()
            dev = (s.rolling(120, min_periods=30).median() - base48).values
            # anti-coupling: flow falling hard => restriction already handles it
            anti_restr = np.full(n, True)
            if self.has("flow_m3_h"):
                q = self.feats["flow_m3_h__mean"].values.astype(float)
                qv = np.where(self.runmask, q, np.nan)
                qs = pd.Series(qv, index=self.t)
                qbase = qs.rolling(2880, min_periods=480).median()
                qdev = (qs.rolling(120, min_periods=30).median() - qbase).values
                qdev_pct = 100.0 * qdev / np.maximum(np.nanmedian(q), 1e-9)
                anti_restr = ~(qdev_pct < -3.0)
            F["clogvfd"] = _sus((dev < SUC_DEV_KPA) & np.asarray(anti_restr, dtype=bool), PERSIST_CLOG) & self.runmask
        if self.has("flow_m3_h"):
            alt = np.full(n, np.nan)
            if self.has("discharge_pressure_kpa"):
                alt = np.fmax(alt, (np.nan_to_num(self.z("discharge_pressure_kpa")) > Z_DIS_UP).astype(float))
            if self.has("motor_speed_rpm"):
                alt = np.fmax(alt, (np.nan_to_num(self.z("motor_speed_rpm")) < Z_SPEED_SAG).astype(float))

            not_air = np.full(n, True)
            if self.has("discharge_pressure_kpa") and self.has("motor_power_kw"):
                not_air = ~((np.nan_to_num(self.z("discharge_pressure_kpa")) < Z_DIS_DOWN - 1) & (np.nan_to_num(self.z("motor_power_kw")) < Z_POWER_DOWN))
            F["restr"] = _sus((self.z("flow_m3_h") < Z_RESTR_FLOW) & (alt == 1.0) & not_air, PERSIST_FAST) & self.runmask
        elif self.has("discharge_pressure_kpa") and self.has("motor_current_a"):
            t0r = (np.nan_to_num(self.z("discharge_pressure_kpa")) > Z_T0_RESTR_DIS) \
                & (np.nan_to_num(self.z("motor_current_a")) < Z_T0_RESTR_CUR)
            F["restr"] = _sus(t0r, PERSIST_FAST) & self.runmask
        if self.has("vibration_crest_factor"):
            hyd_ok = np.full(n, True)
            for c in ("flow_m3_h", "suction_pressure_kpa"):
                if self.has(c):
                    hyd_ok &= np.abs(np.nan_to_num(self.z(c))) < 2.5
            if self.has("motor_power_kw"):
                hyd_ok &= np.nan_to_num(self.z("motor_power_kw")) < 3.0
            crest = self.z("vibration_crest_factor")
            crest_med = pd.Series(np.nan_to_num(crest)).rolling(240, min_periods=60).median().values
            F["bearing_cre"] = _sus((crest_med > Z_CREST - 0.3) & hyd_ok, PERSIST_CREST) & self.runmask
        if self.has("vibration_rms_mm_s"):
            velz = self.z("vibration_rms_mm_s")
            hyd_ok = np.full(n, True)
            for c in ("flow_m3_h", "suction_pressure_kpa", "discharge_pressure_kpa"):
                if self.has(c):
                    hyd_ok &= np.abs(np.nan_to_num(self.z(c))) < 2.5
            if self.has("vibration_accel_rms_g"):
                hyd_ok &= ~(np.nan_to_num(self.z("vibration_accel_rms_g")) > 8.0)
            F["velumb"] = _sus((velz > Z_VEL_UMB) & hyd_ok, PERSIST_VEL) & self.runmask
        F["stuck"], F["noise"], F["step"], F["drift"] = {}, {}, {}, {}
        for c in self.channels:
            if c == "ambient_temp_c":
                continue
            if c in STUCK_EXCL:
                continue
            rng = frozen_range_units(self.feats, self.res, c, win=60)
            if rng is not None:
                F["stuck"][c] = _sus((rng < STUCK_FRAC) & self.run60, PERSIST_STUCK)
            nr = None if c in NOISE_EXCL else rolling_noise_ratio(self.feats, self.res, c, win=60)
            if nr is not None:
                spike = pd.Series(np.abs(np.nan_to_num(self.z(c)))).rolling(PERSIST_FAST * 2, min_periods=5).max().values > SPIKE_Z
                F["noise"][c] = _sus((nr > NOISE_RATIO) & spike, PERSIST_FAST) & self.run60
            zc = np.nan_to_num(self.z(c))
            cov_flat = np.full(n, True)
            for cc in self.COVARIATE.get(c, []):
                if self.has(cc):
                    cov_flat &= np.abs(np.nan_to_num(self.z(cc))) < 1.6
            stable = pd.Series(np.nan_to_num(self.res[f"{c}__z"])).rolling(60, min_periods=20).std().values < 1.0
            F["step"][c] = _sus((np.abs(zc) > Z_STEP) & cov_flat & stable & self._not_clog_trend(c), PERSIST_STEP) & self.run60
            # drift: monotone ramp of x vs trailing 12h median
            if f"{c}__mean" in self.feats.columns and c not in DRIFT_EXCL:
                x = self.feats[f"{c}__mean"].values.astype(float)
                xv = np.where(self.run60, x, np.nan)
                med2 = pd.Series(xv).rolling(120, min_periods=40).median().values
                med12 = pd.Series(xv).rolling(720, min_periods=240).median().values
                dev = med2 - med12
                diff = pd.Series(np.nan_to_num(np.diff(x, prepend=x[0])))
                up = diff.rolling(360, min_periods=120).mean().values
                dn = -diff.rolling(360, min_periods=120).mean().values
                mono = np.maximum(np.nan_to_num(up), np.nan_to_num(dn))
                F["drift"][c] = _sus((np.abs(dev) > DRIFT_DEV) & (mono > DRIFT_MONO) & cov_flat, 90) & self.run60
        # current-drift via load-coupling residual (needs current + power meters)
        if self.has("motor_current_a") and self.has("motor_power_kw"):
            try:
                F["driftcur"] = self._coupling_residual_flag()
            except Exception:
                F["driftcur"] = np.zeros(n, dtype=bool)
        # head-factor residual from the pump curve (needs flow + speed + both gauges + fluid temp)
        F["fh"] = np.zeros(self.n, dtype=bool)
        F["fh_fast"] = np.zeros(self.n, dtype=bool)
        if all(self.has(c) for c in ("flow_m3_h", "motor_speed_rpm", "discharge_pressure_kpa",
                                     "suction_pressure_kpa")):
            try:
                rho = float(ph_water_density(self.a.fluid, 20.0))
                suc = self.feats["suction_pressure_kpa__mean"].values.astype(float)
                dis = self.feats["discharge_pressure_kpa__mean"].values.astype(float)
                H = (dis - suc) * 1e3 / (rho * 9.80665)
                r = np.clip(self.feats["motor_speed_rpm__mean"].values.astype(float) / self.curve.rated_rpm, 0.3, 1.2)
                Q = np.clip(self.feats["flow_m3_h__mean"].values.astype(float), 0.05, 3.0 * self.curve.q_bep)
                with np.errstate(all="ignore"):
                    Hc = self.curve.head_from_Q(Q, r)
                    fh = np.clip(H / np.maximum(Hc, 1e-6), 0.2, 1.5)
                fh[~self.runmask] = np.nan
                fh_med = pd.Series(np.nan_to_num(fh, nan=1.0)).rolling(60, min_periods=20).median().values
                fh_base_8h = pd.Series(np.nan_to_num(fh, nan=1.0)).shift(480).rolling(240, min_periods=60).median().values
                fast_drop = fh_base_8h - fh_med
                base_ok = True
                if self.has("suction_pressure_kpa"):
                    base_ok = np.abs(np.nan_to_num(self.z("suction_pressure_kpa"))) < 2.5
                F["fh"] = np.asarray((fh_med < 0.94) & np.asarray(base_ok, dtype=bool), dtype=bool)
                F["fh_fast"] = np.asarray((fh_med < 0.94) & (fast_drop > 0.03) & np.asarray(base_ok, dtype=bool), dtype=bool)
                self.fh_med = fh_med
            except Exception as ex:
                self.fh_med = None
        else:
            self.fh_med = None
        self.flags = F

    def _coupling_residual_flag(self):
        n = self.n
        fl = np.zeros(n, dtype=bool)
        I = self.feats["motor_current_a__mean"].values.astype(float)
        P = self.feats["motor_power_kw__mean"].values.astype(float)
        P2 = self.feats[f"motor_power_kw__mean"].rolling(120, min_periods=40).median().values
        I2 = self.feats["motor_current_a__mean"].rolling(120, min_periods=40).median().values
        day = np.arange(n, dtype=float) / 1440.0  # minutes grid = days
        sample_idx = []
        sample_val = []
        for gi in range(240, n, 10):
            if not self.run60[gi] or not np.isfinite(P2[gi]) or not np.isfinite(I2[gi]):
                continue
            m = (day[gi] - day <= 1.0) & (day[gi] - day >= 2.0 / 24.0) & self.runmask \
                & np.isfinite(I) & np.isfinite(P)
            Pi, Ii = P[m], I[m]
            if len(Pi) < 300:
                continue
            edges = np.quantile(Pi, [0.2, 0.4, 0.6, 0.8])
            b = int(np.digitize(P2[gi], edges))
            selb = np.digitize(Pi, edges) == b
            if selb.sum() < 30:
                continue
            medI = float(np.median(Ii[selb]))
            madI = float(np.median(np.abs(Ii - np.median(Ii)))) * 1.4826
            resid = I2[gi] - medI
            sample_idx.append(gi)
            sample_val.append(abs(resid) > 3.0 * max(madI, 0.3))
        if not sample_idx:
            return fl
        sv = pd.Series(sample_val)
        sust = sv.rolling(4, min_periods=4).sum().values >= 4 - 0.01
        for k, oksv in zip(sample_idx, sust):
            if oksv:
                j_end = min(k + 10, n)
                fl[max(k - 10, 0):j_end] = True
        return fl & (self.run60 >= 0)

        self.flags = F

    # ---------------- main loop ----------------
    def run(self):
        self._precompute()
        sigma = self.compute_sigma()
        cav_ep = None
        sigma_rearm = None
        if sigma is not None:
            
            
            for _i in range(1):
                pass
            # 5-min sustained cavitation and 15-min re-arm windows
            cav_sus = _sus(np.nan_to_num(sigma, nan=np.inf) < SIGMA_EVENT, 5)
            cav_ok = _sus(np.nan_to_num(sigma, nan=np.inf) > SIGMA_EVENT + 0.01, 6)
        self.prep_snapshots()
        start, end = self.t[0], self.t[-1] + pd.Timedelta("60s")
        grid = pd.date_range(start, end, freq="1min", tz=self.t[0].tz)
        pos_of = {ts: i for i, ts in enumerate(self.t)}
        F = self.flags
        L = self.latch
        last_data = None
        comm_fired = False
        for gt in grid:
            pos = pos_of.get(gt, -1)
            if pos < 0:
                if last_data is not None and (gt - last_data).total_seconds() >= COMM_GAP_MIN * 60:
                    self.fire("COMMUNICATION_LOSS", max(pos, 0),
                              self._ev([], 0, extra=f"telemetry missing since {last_data} (>= {COMM_GAP_MIN} min)"),
                              event_class="SENSOR", conf=0.8, alert_time=gt)
                continue
            last_data = gt
            # snapshot consumption
            if self.snap_metrics is not None:
                while self._snap_cursor < len(self.snap_metrics) \
                        and pd.Timestamp(self.snap_metrics.timestamp_utc.iloc[self._snap_cursor]) <= gt:
                    self.handle_snapshot(self.snap_metrics.iloc[self._snap_cursor], pos, gt)
                    self._snap_cursor += 1
            mode = self.feats["operating_mode"].iloc[pos]
            if mode != "RUNNING":
                if self.pending_vel is not None and (gt - self.t[self.pending_vel[0]]).total_seconds() > VEL_HOLD_SNAP * 60:
                    self.fire("UNKNOWN", pos,
                              self._ev(["vibration_rms_mm_s"], pos, extra="vibration elevated"),
                              event_class="MACHINE", conf=self.pending_vel[1])
                    self.pending_vel = None
                continue
            storm = bool(self.ctx is not None and np.isfinite(self.ctx["sea_state_hs_m"].iloc[pos])
                         and self.ctx["sea_state_hs_m"].iloc[pos] >= 2.5)
            fired_machine = False
            # cavitation (highest hydraulic priority; self-latching, re-arms between episodes)
            if sigma is not None and not storm:
                if cav_sus[pos] and (("CAVITATION" not in L) or cav_ok[pos]):
                    if "CAVITATION" in L:
                        L.pop("CAVITATION")
                    self.fire("CAVITATION", pos,
                              self._ev(["suction_pressure_kpa", "discharge_pressure_kpa"], pos,
                                       extra=f"NPSH margin ~{sigma[pos]:.2f}"), conf=0.8)
                    fired_machine = True
            # clog rules
            if not storm and not fired_machine and F.get("clogfs") is not None and F["clogfs"][pos]:
                if self.fire("SUCTION_STRAINER_CLOGGING", pos,
                             self._ev(["suction_pressure_kpa"], pos, extra="suction loss at steady speed"), conf=0.7):
                    fired_machine = F["clogfs"][pos]
            vib_mach_open = any(k in L for k in ("BEARING_WEAR", "MISALIGNMENT", "IMBALANCE", "UNKNOWN"))
            if (not storm) and (not fired_machine) and (not vib_mach_open) \
                    and F.get("clogvfd") is not None and F["clogvfd"][pos]:
                if self.fire("SUCTION_STRAINER_CLOGGING", pos,
                             self._ev(["suction_pressure_kpa", "motor_speed_rpm", "motor_power_kw"], pos,
                                      extra="suction-loss trend with drive compensation"), conf=0.65):
                    fired_machine = True
            # restriction
            if not storm and not fired_machine and F.get("restr") is not None and F["restr"][pos]:
                pairs = ["flow_m3_h", "discharge_pressure_kpa", "motor_power_kw"]
                if self.fire("DISCHARGE_RESTRICTION", pos, self._ev(pairs, pos), conf=0.75):
                    fired_machine = True
            # air
            if not storm and not fired_machine and F.get("air") is not None and F["air"][pos]:
                if self.fire("AIR_ENTRAINMENT", pos,
                             self._ev(["flow_m3_h", "discharge_pressure_kpa", "motor_power_kw"], pos,
                                      extra="hydraulic collapse, NPSH margin ok"), conf=0.7):
                    fired_machine = True
            # machine-unknown hydraulic (only when nothing matched and no hydraulic latch)
            hyd_latch_open = any(k in L for k in ("DISCHARGE_RESTRICTION", "SUCTION_STRAINER_CLOGGING",
                                                  "AIR_ENTRAINMENT", "CAVITATION"))
            if not fired_machine and (not hyd_latch_open) and F.get("unkhyd") is not None and F["unkhyd"][pos]:
                if self.fire("UNKNOWN", pos,
                             self._ev(["discharge_pressure_kpa", "motor_power_kw"], pos,
                                      extra="hydraulic deviation, cause ambiguous"),
                             event_class="MACHINE", conf=0.5):
                    fired_machine = True
            # bearing via crest
            if F.get("bearing_cre") is not None and F["bearing_cre"][pos]:
                pairs = ["vibration_crest_factor"]
                if self.has("vibration_accel_rms_g"):
                    pairs.append("vibration_accel_rms_g")
                self.fire("BEARING_WEAR", pos, self._ev(pairs, pos, extra="crest jump, hydraulics flat"), conf=0.65)
            # velocity umbrella (suppressed once a vibration-domain machine type is latched)
            if any(k in L for k in ("BEARING_WEAR", "MISALIGNMENT", "IMBALANCE")):
                self.pending_vel = None
            if F.get("velumb") is not None and F["velumb"][pos]:
                if self.pending_vel is None:
                    self.pending_vel = (pos, float(np.clip(0.55 + 0.04 * abs(self.pct("vibration_rms_mm_s", pos)), 0.5, 0.8)))
                else:
                    j, conf = self.pending_vel
                    if (gt - self.t[j]).total_seconds() > VEL_HOLD_SNAP * 60:
                        self.fire("UNKNOWN", pos,
                                  self._ev(["vibration_rms_mm_s"], pos, extra="vibration elevated, spectrum pending"),
                                  event_class="MACHINE", conf=conf)
                        self.pending_vel = (pos, conf)
            # sensor flags
            for c, arr in F["stuck"].items():
                if arr[pos]:
                    self.fire("SENSOR_STUCK", pos,
                              self._ev([], pos, extra=f"{c} frozen (60-min range < {STUCK_FRAC:.0%} of noise)"),
                              event_class="SENSOR", conf=0.75)
                    break
            for c, arr in F["noise"].items():
                if arr[pos]:
                    self.fire("SENSOR_NOISE_SPIKES", pos,
                              self._ev([], pos, extra=f"{c}: std > {NOISE_RATIO:.0f}x noise, spikes > {SPIKE_Z:.0f} sigma"),
                              event_class="SENSOR", conf=0.7)
                    break
            step_drift_on = {c for c, arr in F["drift"].items() if arr[pos]}
            for c, arr in F["step"].items():
                if c in step_drift_on:
                    continue
                if arr[pos]:
                    if c == "suction_pressure_kpa" and any(k in L for k in ("SUCTION_STRAINER_CLOGGING", "CAVITATION")):
                        continue
                    self.fire("SENSOR_CALIBRATION_SHIFT", pos,
                              self._ev([], pos, extra=f"{c} stepped > {Z_STEP:.1f} sigma, coupled channels flat"),
                              event_class="SENSOR", conf=0.7)
                    break
            if F.get("fh") is not None and F["fh"][pos] and "UNKHYD" not in L:
                fh_reason = "head-factor below pump curve" + (", rapid drop" if F["fh_fast"][pos] else "")
                if F["fh_fast"][pos]:
                    self.fire("AIR_ENTRAINMENT", pos,
                              self._ev([], pos, extra=fh_reason), event_class="MACHINE", conf=0.65)
                else:
                    self.fire("UNKNOWN", pos, self._ev([], pos, extra=fh_reason),
                              event_class="MACHINE", conf=0.55)
            for c, arr in F["drift"].items():
                if any(k in L for k in ("BEARING_WEAR", "MISALIGNMENT", "IMBALANCE")):
                    break
                if arr[pos]:
                    self.fire("SENSOR_DRIFT", pos,
                              self._ev([], pos, extra=f"{c}: monotone ramp > {DRIFT_DEV:.1f} MAD vs trailing 12 h"),
                              event_class="SENSOR", conf=0.65)
                    break
        out = pd.DataFrame(self.alerts)
        return out
