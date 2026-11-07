"""Improved diagnostician on top of the B1 detector (causal: only data <= alert time)."""
import numpy as np, pandas as pd
from retrofit_sim import baselines as B
CH = B.CH; COUPLED = B.COUPLED
THERMAL = {"bt", "wt", "tf"}
def _ns(s):
    """same time resolution everywhere (newer pandas refuses to merge ms with us timestamps)"""
    return pd.to_datetime(s, utc=True).astype("datetime64[ns, UTC]")

def prep(zf, ctx, snapf, assets=None):
    """per-asset helper columns: minutes since start, length of preceding stop, context, vibration ratios"""
    out = []
    for a, g in zf.groupby("asset_id", sort=False):
        g = g.sort_values("window_start_utc").reset_index(drop=True)
        g["window_start_utc"] = _ns(g["window_start_utc"])
        run = ((g.operating_mode == "RUNNING") & (g.running_fraction >= 0.99)).values
        since = np.zeros(len(g)); stop_len = np.zeros(len(g)); s = 0; off = 0; last_stop = 0
        for j, x in enumerate(run):
            if x:
                if s == 0: last_stop = off
                s += 1; off = 0
            else:
                off += 1; s = 0
            since[j] = s; stop_len[j] = last_stop
        g["since_start"] = since; g["prev_stop_min"] = stop_len
        c = ctx[ctx.asset_id == a].sort_values("t").copy(); c["t"] = _ns(c["t"])
        g = pd.merge_asof(g, c[["t", "sea_state_hs_m", "suction_static_head_m"]], left_on="window_start_utc", right_on="t", direction="backward").drop(columns="t")
        sf = snapf[snapf.asset_id == a].sort_values("time").copy()
        if len(sf): sf["time"] = _ns(sf["time"])
        if len(sf):
            g = pd.merge_asof(g, sf[["time", "r_bpfo", "r_1x", "r_2x", "r_hf", "b_idx", "r_bidx"]], left_on="window_start_utc", right_on="time", direction="backward").drop(columns="time")
        else:
            for k in ("r_bpfo", "r_1x", "r_2x", "r_hf", "b_idx", "r_bidx"): g[k] = np.nan
        if assets is not None:
            g = add_physics(g, assets.set_index("asset_id").loc[a])
        out.append(g)
    return pd.concat(out, ignore_index=True)

G = 9.81
def _rho(fluid):
    f = str(fluid).lower()
    return 1004.0 if "sea" in f else (975.0 if "hot" in f else 1000.0)

def add_physics(g, s):
    """Pump-curve physics from the datasheet (assets.csv) - no per-pump tuning.
    ph_Ht : head / (rated head * r^2)         affinity law H ~ n^2
    ph_fH : measured head / pump-curve head   needs flow meter; 1.0 = healthy, <1 = head loss
    ph_dH, ph_dP : change of normalised head / power (P/r^3, or current) vs first day of running"""
    rho = _rho(s.fluid); h0 = s.pump_shutoff_head_m / s.pump_rated_head_m
    sp = g.get("motor_speed_rpm__mean")
    r = (sp / s.motor_rated_rpm) if sp is not None and sp.notna().any() else pd.Series(1.0, index=g.index)
    r = r.clip(lower=0.3)
    ps = g.get("suction_pressure_kpa__mean")
    if ps is None or ps.isna().all():                      # T0: no suction gauge
        if "LT_FRESH" in str(s.profile): ps = pd.Series(120.0, index=g.index)   # closed loop held at 120 kPa
        else: ps = rho * G * g["suction_static_head_m"].ffill().bfill().fillna(2.5) / 1000
    H = (g["discharge_pressure_kpa__mean"] - ps) * 1000 / (rho * G)
    g["ph_Ht"] = H / (s.pump_rated_head_m * r ** 2)
    fl = g.get("flow_m3_h__mean")
    if fl is not None and fl.notna().any():
        q = fl / (r * s.pump_rated_flow_m3_h)
        g["ph_q"] = q
        g["ph_fH"] = g["ph_Ht"] / (h0 - (h0 - 1) * q.clip(0, 1.6) ** 2)
    else:
        g["ph_q"] = np.nan; g["ph_fH"] = np.nan
    pw = g.get("motor_power_kw__mean")
    Pn = (pw / r ** 3) if pw is not None and pw.notna().any() else g["motor_current_a__mean"] / r ** 2
    ok = g["steady"].astype(bool) & (g["since_start"] >= 120)
    first = ok & (ok.cumsum() <= 24 * 60)                  # first 24 h of settled running = reference
    for name, x in (("ph_dH", g["ph_Ht"]), ("ph_dP", Pn), ("ph_dfH", g["ph_fH"])):
        ref = x.where(first).expanding().median().ffill()
        g[name] = x.rolling(30, min_periods=10).median() / ref - 1
    fm = g["ph_fH"].rolling(30, min_periods=10).median()
    g["ph_dfH6h"] = fm / fm.shift(360) - 1                 # change of head factor over the last 6 h
    # NPSH margin (cavitation): Antoine vapour pressure of water, gauge -> absolute, velocity head
    T = g["fluid_temp_c__mean"]
    pv = 10 ** (8.07131 - 1730.63 / (233.426 + T)) * 0.133322          # kPa abs
    qn = (fl / (r * s.pump_rated_flow_m3_h)).fillna(1.0) if fl is not None and fl.notna().any() else pd.Series(1.0, index=g.index)
    v = 2.5 * qn * r                                                       # suction line sized for 2.5 m/s at BEP
    psg = g.get("suction_pressure_kpa__mean")
    if psg is not None and psg.notna().any():
        npsha = ((psg + 101.3 - pv) * 1000 + 0.5 * rho * v ** 2) / (rho * G)
        g["ph_sigma"] = npsha / (s.npsh3_at_bep_m * r ** 2 * (0.55 + 0.45 * qn.clip(0, 1.6) ** 2.6))
    else:
        g["ph_sigma"] = np.nan
    # STEP 1 - fixed physics references (a slow drift cannot drag them along like B1's 24 h baseline)
    early = ok & (ok.cumsum() <= 360)                       # first 6 h of settled running
    g["ph_iP_res"] = np.nan
    if pw is not None and pw.notna().any() and early.sum() > 60:
        # motor current = magnetising current + part proportional to power
        X = np.c_[np.ones(early.sum()), pw[early], r[early]]
        b, *_ = np.linalg.lstsq(X, g["motor_current_a__mean"][early], rcond=None)
        i0 = b[0] + b[2] * r[early].median()                   # current at zero power = magnetising current
        P_span = pw[early].quantile(0.95) / max(pw[early].quantile(0.05), 1e-6)
        physical = (0.2 * s.motor_rated_current_a <= i0 <= 0.6 * s.motor_rated_current_a) and b[1] > 0 and P_span > 1.05
        if not physical:                                       # reference too narrow / unphysical -> use rated-motor line
            i0 = 0.35 * s.motor_rated_current_a; slope = (s.motor_rated_current_a - i0) / s.motor_rated_kw
            k_fit = np.median((g["motor_current_a__mean"][early] - i0) / pw[early].clip(lower=1e-3) / slope)
            b = np.array([i0, slope * k_fit, 0.0])
        res = (g["motor_current_a__mean"] - (b[0] + b[1] * pw + b[2] * r)) / g["motor_current_a__mean"][early].median()
        g["ph_iP_res"] = res.where(ok).rolling(60, min_periods=30).median()
    bt = g.get("bearing_temp_c__mean")
    g["ph_bt_dev"] = np.nan; g["ph_bt_same_h"] = 0.0
    if bt is not None and bt.notna().any():
        d = bt.ffill() - g["fluid_temp_c__mean"]               # bearing runs a fixed amount above the water it pumps
        g["ph_bt_dev"] = (d - d.where(first).median()).where(ok).rolling(60, min_periods=30).median()
        x = bt.ffill(); chg = x.diff().fillna(1).ne(0)
        last_chg = g["window_start_utc"].where(chg).ffill()
        g["ph_bt_same_h"] = (g["window_start_utc"] - last_chg).dt.total_seconds() / 3600
    # STEP 2 - look inside the minute: max - min range vs this pump's normal range
    for c in ("flow_m3_h", "discharge_pressure_kpa", "suction_pressure_kpa", "motor_current_a", "motor_power_kw", "motor_speed_rpm"):
        if c + "__max" in g and g[c + "__max"].notna().any():
            rng = g[c + "__max"] - g[c + "__min"]
            ref = rng.where(first).quantile(0.99)
            g["ph_rr_" + c] = rng / ref if ref and ref > 0 else np.nan
    g["ph_has_flow"] = fl is not None and fl.notna().any()
    return g

def snap_ratios(vf):
    """vibration feature ratios vs each asset's first 3 snapshots (causal baseline)"""
    vf = vf.copy(); vf["time"] = pd.to_datetime(vf["time"], utc=True)
    out = []
    for a, g in vf.groupby("asset_id"):
        g = g.sort_values("time"); b = g.head(3)
        for k, col in (("bpfo", "env_bpfo"), ("1x", "a_1x"), ("2x", "a_2x"), ("hf", "hf_rms")):
            g["r_" + k] = g[col] / max(b[col].median(), 1e-9)
        g["b_idx"] = g["env_bpfo"] / g["hf_rms"].clip(lower=1e-6)
        g["r_bidx"] = g["b_idx"] / max(g["b_idx"].head(3).median(), 1e-6)
        out.append(g)
    return pd.concat(out)

def _step_or_ramp(g, j, c):
    """SENSOR_CALIBRATION_SHIFT if most of the change came in one ~10-min jump, else SENSOR_DRIFT"""
    z = g["z_" + c].iloc[max(0, j - 360): j + 1].astype(float).ffill().fillna(0).values
    if len(z) < 30: return "SENSOR_CALIBRATION_SHIFT"
    total = abs(z[-1] - np.median(z[:20]))
    jumps = np.abs(z[10:] - z[:-10]); big = np.nanmax(jumps) if len(jumps) else 0
    return "SENSOR_CALIBRATION_SHIFT" if total < 1e-6 or big > 0.6 * total else "SENSOR_DRIFT"

def diagnose2(g, j, k, ctl):
    r = g.iloc[j]
    flag = lambda key: (not pd.isna(r.get(key, False))) and bool(r.get(key, False))
    if flag("gap"):
        return "SENSOR", "COMMUNICATION_LOSS", 0.95, "missing rows", "Check gateway / network; data gap."
    warm = r["since_start"] >= 120            # thermal channels unreliable for ~2 h after a start
    z = {c: (0.0 if pd.isna(r.get("z_" + c)) else float(r["z_" + c])) for c in CH}
    if not warm:
        for c in THERMAL: z[c] = 0.0
    for c in z:
        if flag("flat_" + c) and flag("steady") and c in ("pd", "ps", "q", "bt", "i", "tf", "wt"):
            return "SENSOR", "SENSOR_STUCK", 0.9, f"{CH[c]} frozen while pump running", f"Check transmitter {CH[c]}."
    # --- noise spikes: ONE channel's in-minute spread explodes (average unchanged), all others calm
    zsv = {c: float(r["zs_" + c]) for c in CH if "zs_" + c in r.index and not pd.isna(r["zs_" + c])}
    if zsv:
        top = max(zsv, key=zsv.get)
        if zsv[top] > 15 and all(v < 5 for c, v in zsv.items() if c != top):
            return "SENSOR", "SENSOR_NOISE_SPIKES", 0.8, f"{CH[top]} in-minute spread z={zsv[top]:.0f}, all other channels calm (<5)", f"Check cabling / grounding of {CH[top]}."
    # --- single-instrument deviations -> sensor faults
    for c in sorted(z, key=lambda c: -abs(z[c])):
        if abs(z[c]) <= k or c not in COUPLED or c in ("v", "a", "c"): continue
        if c == "ps" and z[c] < 0: continue          # suction drop alone = early strainer clogging
        cpl = [abs(z[x]) for x in COUPLED[c] if not pd.isna(r.get("z_" + x))]
        if cpl and max(cpl) < max(k / 3, abs(z[c]) / 6):
            zs = r.get("zs_" + c, 0.0)
            if not pd.isna(zs) and zs > k:
                return "SENSOR", "SENSOR_NOISE_SPIKES", 0.8, f"{CH[c]} noisy, others normal", f"Check cabling / grounding of {CH[c]}."
            ft = _step_or_ramp(g, j, c)
            return "SENSOR", ft, 0.75, f"{CH[c]} deviates alone (z={z[c]:+.1f})", f"Verify {CH[c]} against a reference gauge; recalibrate."
    big = {c for c, v in z.items() if abs(v) > k}
    ev = ", ".join(f"{CH[c]} z={z[c]:+.1f}" for c in sorted(big, key=lambda c: -abs(z[c]))[:3])
    rb, r1, r2, rh = (r.get(x) for x in ("r_bpfo", "r_1x", "r_2x", "r_hf"))
    nz = lambda v: 0.0 if v is None or pd.isna(v) else float(v)
    rb, r1, r2, rh = nz(rb), nz(r1), nz(r2), nz(rh)
    bidx = nz(r.get("b_idx"))
    post_maint = r["since_start"] < 24 * 60 and r["prev_stop_min"] >= 30
    # --- mechanical (vibration evidence)
    rbidx = nz(r.get("r_bidx"))
    sig0 = nz(r.get("ph_sigma")) if not pd.isna(r.get("ph_sigma", np.nan)) else 99.0
    accel_is_cav = sig0 < 1.3 or (r.get("b_idx") is not None and not pd.isna(r.get("b_idx")) and bidx < 0.25 and z["ps"] < -k)
    if bidx > 0.6 or (bidx > 0.25 and rbidx > 3) or (z["c"] > k and not accel_is_cav) or (not accel_is_cav and z["a"] > k and (z["c"] > k / 2 or z["bt"] > k / 2 or z["a"] > 2 * k)):
        return "MACHINE", "BEARING_WEAR", 0.85, ev + f"; bearing-defect index {bidx:.2f} (healthy ~0.1), crest z={z['c']:+.1f}", "Plan bearing replacement; check lubrication."
    hyd = max(abs(z[c]) for c in ("ps", "pd", "q", "n", "pw"))
    vib_now = max(z["v"], z["a"])
    if z["v"] > k / 2 or ((r2 > 3 or r1 > 3) and not (hyd > k and hyd > vib_now)):   # old vibration + new hydraulic change -> look at hydraulics
        two_x = r2 > max(2.0, 0.8 * r1)                     # misalignment = 2x running-speed component
        hot = z["wt"] > k / 2 or z["bt"] > k / 2            # coupling forces heat bearings / winding
        if two_x or hot or (post_maint and r1 < 2.5 and r2 > 1.3):
            return "MACHINE", "MISALIGNMENT", 0.7, ev + f"; 2x vibration x{r2:.1f}; restart after {r['prev_stop_min']:.0f} min stop", "Check coupling alignment (likely after maintenance)."
        return "MACHINE", "IMBALANCE", 0.65, ev + f"; 1x vibration x{r1:.1f}", "Inspect impeller for fouling; balance."
    # --- hydraulic (pump-curve physics)
    fH = r.get("ph_fH"); dH = nz(r.get("ph_dH")); dP = nz(r.get("ph_dP"))
    has_fH = fH is not None and not pd.isna(fH)
    dfH = nz(r.get("ph_dfH"))
    headloss = (fH < 0.90 or dfH < -0.03) if has_fH else (dH < -0.05 and dP > -0.03)
    phys = (f"; head factor {fH:.2f} ({dfH*100:+.0f}% vs own normal)" if has_fH else "") + f"; head {dH*100:+.0f}% power {dP*100:+.0f}% vs reference"
    ev = ev + phys
    hs = nz(r.get("sea_state_hs_m")); lvl = r.get("suction_static_head_m")
    erratic = nz(r.get("zs_pd")) > k / 2 or nz(r.get("zs_ps")) > k / 2 or nz(r.get("zs_q")) > k / 2
    if (hs >= 2.5 or erratic or (not pd.isna(lvl) and lvl < 1.0)) and (z["pd"] < -k / 2 or z["q"] < -k / 2 or headloss):
        return "MACHINE", "AIR_ENTRAINMENT", 0.6, ev + f"; sea state {hs:.1f} m" , "Check sea-chest venting / basin level; air in suction."
    sig = r.get("ph_sigma")
    if sig is not None and not pd.isna(sig) and sig < 1.15 and z["ps"] > -k:   # strong suction drop = clogging is the root cause
        return "MACHINE", "CAVITATION", 0.85, ev + f"; NPSH margin {sig:.2f} (cavitates below 1.15, healthy > 3)", "Raise suction level / clean strainer / reduce flow; water near boiling at pump inlet."
    if z["vp"] > k / 2 and z["ps"] < -k / 4:
        return "MACHINE", "SUCTION_STRAINER_CLOGGING", 0.7, ev + "; control valve opening to hold flow while suction pressure falls", "Inspect / clean suction strainer."
    if z["vp"] > k / 2 and abs(z["ps"]) <= k / 4:
        return "MACHINE", "DISCHARGE_RESTRICTION", 0.6, ev + "; control valve opening to hold flow, suction normal -> resistance downstream", "Check discharge valves and heat-exchanger fouling."
    if z["ps"] < -k and (z["a"] > k or rh > 3):
        return "MACHINE", "CAVITATION", 0.7, ev, "Check suction strainer / level; reduce flow if allowed."
    if z["ps"] < -k / 2 and (z["pd"] <= 0 or z["n"] > 0 or z["q"] < 0):
        return "MACHINE", "SUCTION_STRAINER_CLOGGING", 0.75, ev, "Inspect / clean suction strainer."
    fast = nz(r.get("ph_dfH6h")) < -0.02                 # head lost within hours -> air / cavitation, not wear
    if headloss and has_fH and fast and z["ps"] > -k / 2:
        return "MACHINE", "AIR_ENTRAINMENT", 0.55, ev + f"; head factor fell {nz(r.get('ph_dfH6h'))*100:.0f}% in 6 h (too fast for wear)", "Check sea-chest venting / basin level; air in suction."
    if headloss and has_fH and z["ps"] > -k / 2:
        return "MACHINE", "IMPELLER_WEAR", 0.6, ev, "Performance test; inspect impeller / wear rings."
    if (z["pd"] > k / 2 and (z["q"] < -k / 2 or z["i"] < -k / 2 or z["pw"] < -k / 2)) or (dH > 0.04 and dP < -0.03):
        return "MACHINE", "DISCHARGE_RESTRICTION", 0.75, ev, "Check discharge valves and heat-exchanger fouling."
    if z["q"] < -k and z["n"] <= k / 2 and not headloss:
        return "MACHINE", "DISCHARGE_RESTRICTION", 0.6, ev, "Check discharge valves and heat-exchanger fouling."
    if z["pd"] < -k / 2 and z["i"] <= 0:
        return "MACHINE", "IMPELLER_WEAR", 0.5, ev, "Performance test; inspect impeller / wear rings."
    if z["n"] > k or z["pw"] > k:
        return "MACHINE", "SUCTION_STRAINER_CLOGGING", 0.5, ev, "Inspect / clean suction strainer."
    if headloss or (not has_fH and nz(r.get("ph_Ht")) and nz(r.get("ph_Ht")) < 0.95 and z["i"] <= k / 2):
        return "MACHINE", "IMPELLER_WEAR", 0.4, ev + f"; head only {nz(r.get('ph_Ht'))*100:.0f}% of datasheet", "Performance test; inspect impeller / wear rings."
    return "MACHINE", "UNKNOWN", 0.3, ev, "Inspect pump; cause unclear."

def detect(zp, assets, k=6.0, persist=15):
    ctl = dict(zip(assets.asset_id, assets.control))
    rows = []
    for a, g in zp.groupby("asset_id", sort=False):
        g = g.reset_index(drop=True)
        gw = g.copy(); cold = gw["since_start"] < 120          # physics: motor/bearing still warming up
        for c in THERMAL:
            if "z_" + c in gw: gw.loc[cold, "z_" + c] = 0.0
        zm = B._zmax(gw, k)
        flag = (g["steady"].values & (zm > k)) | g["gap"].values | B._flat_any(g)
        run, last = 0, {}
        for j in range(len(g)):
            run = run + 1 if flag[j] else 0
            if run == persist or (run > persist and (run - persist) % 720 == 0):
                t = g["window_start_utc"].iloc[j] + pd.Timedelta(minutes=1)
                cls, ft, conf, evd, act = diagnose2(g, j, k, ctl.get(a))
                if ft not in last or t - last[ft] > B.REFRACTORY:
                    rows.append({"asset_id": a, "alert_time_utc": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "event_class": cls,
                                 "fault_type": ft, "confidence": conf, "evidence": evd, "recommended_action": act})
                    last[ft] = t
    rows += physics_alerts(zp, rows, k, ctl)
    rows.sort(key=lambda x: (x["asset_id"], x["alert_time_utc"]))
    keep, last = [], {}                              # don't nag: same fault on same pump only once per 12 h
    for x in rows:
        key = (x["asset_id"], x["fault_type"]); t = pd.Timestamp(x["alert_time_utc"])
        if x["fault_type"] != "CAVITATION" and key in last and t - last[key] < B.REFRACTORY:
            continue
        last[key] = t; keep.append(x)
    al = pd.DataFrame(keep, columns=B._COLS)
    return _post_relabel(al, zp, ctl, k)

def _post_relabel(al, zp, ctl, k=6.0):
    """Refractory-preserving physics tie-breakers applied after suppression rhythm is fixed."""
    if not len(al): return al
    al = al.copy()
    nz = lambda v: 0.0 if v is None or pd.isna(v) else float(v)
    for idx, row in al.iterrows():
        ft, a = row["fault_type"], row["asset_id"]
        if ft == "SENSOR_NOISE_SPIKES" and any(vch in str(row["evidence"]) for vch in ("vibration_rms_mm_s", "vibration_accel_rms_g", "vibration_crest_factor")):
            t = pd.Timestamp(row["alert_time_utc"]) - pd.Timedelta(minutes=1)
            m = zp[(zp.asset_id == a) & (zp.window_start_utc == t)]
            if len(m):
                r = m.iloc[0]
                if nz(r.get("ph_dH")) > 0.04 and nz(r.get("ph_dP")) < -0.03:
                    al.at[idx, "event_class"] = "MACHINE"
                    al.at[idx, "fault_type"] = "DISCHARGE_RESTRICTION"
                    al.at[idx, "confidence"] = 0.75
                    al.at[idx, "recommended_action"] = "Check discharge valves and heat-exchanger fouling."
        elif ft == "UNKNOWN":
            t = pd.Timestamp(row["alert_time_utc"]) - pd.Timedelta(minutes=1)
            m = zp[(zp.asset_id == a) & (zp.window_start_utc == t)]
            if len(m):
                r = m.iloc[0]
                zpd, zi, zpw = nz(r.get("z_pd")), nz(r.get("z_i")), nz(r.get("z_pw"))
                dH = nz(r.get("ph_dH"))
                hyd = max(abs(nz(r.get("z_" + c))) for c in ("ps", "pd", "q", "n", "pw"))
                if hyd < k / 2:
                    al.at[idx, "fault_type"] = "BEARING_WEAR"
                    al.at[idx, "confidence"] = 0.65
                elif zpd < -k / 2 and zi > 0:
                    al.at[idx, "fault_type"] = "SUCTION_STRAINER_CLOGGING"
                    al.at[idx, "confidence"] = 0.65
                elif (ctl.get(a) == "VFD_PRESSURE" and zpw < -k / 2 and zi < -k / 2) or (zpd > k / 2 and dH >= 0.04):
                    al.at[idx, "fault_type"] = "DISCHARGE_RESTRICTION"
                    al.at[idx, "confidence"] = 0.65
    return al

def physics_alerts(zp, existing, k, ctl, hold=10):
    """Alerts fired by physics even when no single z-score is extreme:
    cavitation (NPSH margin < 1.15 for 5 min, one alert per episode), bearing index crossing, fast head loss."""
    out = []
    ex = {}
    for x in existing: ex.setdefault(x["asset_id"], []).append(pd.Timestamp(x["alert_time_utc"]))
    for a, g in zp.groupby("asset_id", sort=False):
        g = g.reset_index(drop=True)
        ts_arr = list(g["window_start_utc"])
        run = g["operating_mode"].eq("RUNNING").values
        steady = g["steady"].values
        sig = g["ph_sigma"].values if "ph_sigma" in g else np.full(len(g), np.nan)
        bidx = g["b_idx"].values if "b_idx" in g else np.full(len(g), np.nan)
        rbx = g["r_bidx"].values if "r_bidx" in g else np.full(len(g), np.nan)
        dfh = g["ph_dfH"].values if "ph_dfH" in g else np.full(len(g), np.nan)
        ht = g["ph_Ht"].values if "ph_Ht" in g else np.full(len(g), np.nan)
        zi_arr = np.nan_to_num(g["z_i"].values, nan=0.0) if "z_i" in g else np.zeros(len(g))
        zps_arr = np.nan_to_num(g["z_ps"].values, nan=0.0) if "z_ps" in g else np.zeros(len(g))
        zv_abs = np.abs(np.nan_to_num(g["z_v"].values, nan=0.0)) if "z_v" in g else np.zeros(len(g))
        za_abs = np.abs(np.nan_to_num(g["z_a"].values, nan=0.0)) if "z_a" in g else np.zeros(len(g))
        has_fh_col = bool(g["ph_fH"].notna().any()) if "ph_fH" in g else False
        cav_n = 0; in_ep = False; brg_done = False; hl_n = 0; last_hl = None; ht_n = 0; ht_done = False
        # vibration recordings (every ~4 h): 2x line = misalignment, 1x line = imbalance
        r1s = g["r_1x"].values if "r_1x" in g else np.full(len(g), np.nan)
        r2s = g["r_2x"].values if "r_2x" in g else np.full(len(g), np.nan)
        snap_hist = []; vib_done = {}
        rr_cols = [c for c in g.columns if c.startswith("ph_rr_")]
        RR = g[rr_cols].values if rr_cols else np.zeros((len(g), 0))
        spike_hist = {}; last_sens = {}
        ipr = g["ph_iP_res"].values if "ph_iP_res" in g else np.full(len(g), np.nan)
        btd = g["ph_bt_dev"].values if "ph_bt_dev" in g else np.full(len(g), np.nan)
        bts = g["ph_bt_same_h"].values if "ph_bt_same_h" in g else np.zeros(len(g))
        ip_n = 0; bt_n = 0
        def sens_ok(key, t, once=False):
            if key in last_sens and (once or t - last_sens[key] < B.REFRACTORY): return False
            last_sens[key] = t; return True
        for j in range(len(g)):
            t = ts_arr[j] + pd.Timedelta(minutes=1)
            near = any(abs((t - e).total_seconds()) < 600 for e in ex.get(a, []))
            fire = None
            low = run[j] and not np.isnan(sig[j]) and sig[j] < 1.15
            cav_n = cav_n + 1 if low else 0
            if in_ep and not np.isnan(sig[j]) and sig[j] > 1.3: in_ep = False
            if cav_n == hold and not in_ep:
                in_ep = True
                fire = ("CAVITATION", 0.85, f"NPSH margin {sig[j]:.2f} < 1.15 for {hold} min (water near boiling at inlet)", "Raise suction level / clean strainer / reduce flow.")
            if not brg_done and not np.isnan(bidx[j]) and (bidx[j] > 0.6 or (bidx[j] > 0.25 and rbx[j] > 3)):
                brg_done = True
                fire = fire or ("BEARING_WEAR", 0.8, f"bearing-defect index {bidx[j]:.2f} (healthy ~0.1, x{rbx[j]:.1f} vs start)", "Plan bearing replacement; check lubrication.")
            hl = run[j] and steady[j] and not np.isnan(dfh[j]) and dfh[j] < -0.05
            hl_n = hl_n + 1 if hl else 0
            if hl_n == 30 and (last_hl is None or t - last_hl > B.REFRACTORY):
                last_hl = t
                fire = fire or ("IMPELLER_WEAR", 0.5, f"head factor {dfh[j]*100:.0f}% below own normal for 30 min", "Performance test; inspect impeller / wear rings.")
            if not has_fh_col and ctl.get(a) == "FIXED_SPEED" and not ht_done:
                ht_low = run[j] and steady[j] and not np.isnan(ht[j]) and ht[j] < 0.94 and zi_arr[j] <= k / 2 and zps_arr[j] > -k / 2
                ht_n = ht_n + 1 if ht_low else 0
                if ht_n == 60:
                    ht_done = True
                    fire = fire or ("IMPELLER_WEAR", 0.5, f"head only {ht[j]*100:.0f}% of datasheet rated head for 60 steady min", "Performance test; inspect impeller / wear rings.")
            # --- vibration recording rule: same verdict on two recordings in a row (for subtle T1/untriggered vibration)
            if j > 0 and not np.isnan(r2s[j]) and (r2s[j] != r2s[j - 1] or r1s[j] != r1s[j - 1]):
                v = ("MISALIGNMENT" if r2s[j] > 3.5 else ("IMBALANCE" if (r1s[j] > 2.5 and r2s[j] < 1.5) else None)) if za_abs[j] < k else None
                snap_hist.append(v); snap_hist[:] = snap_hist[-2:]
                if v and snap_hist == [v, v] and run[j] and not fire and v not in vib_done:
                    vib_done[v] = t
                    fire = (v, 0.75, f"vibration recording: 1x line x{r1s[j]:.1f}, 2x line x{r2s[j]:.1f} vs start, two recordings in a row "
                            + ("(twice-per-turn wobble = shaft misalignment)" if v == "MISALIGNMENT" else "(once-per-turn wobble = imbalance)"),
                            "Check coupling alignment." if v == "MISALIGNMENT" else "Inspect impeller for fouling; balance.")
            # --- STEP 2: noise spikes = ONE channel's in-minute range explodes, the others stay normal
            if run[j] and RR.shape[1]:
                row = RR[j]; big = [i for i, v in enumerate(row) if not np.isnan(v) and v > 2.5]
                for i in range(RR.shape[1]):
                    h = spike_hist.setdefault(i, []); h.append(1 if (big == [i]) else 0)
                    if len(h) > 15: h.pop(0)
                    if sum(h) >= 5 and not fire and sens_ok("spk" + rr_cols[i], t):
                        ch = rr_cols[i][6:]
                        fire = ("SENSOR_NOISE_SPIKES", 0.75, f"{ch}: in-minute range x{row[i]:.1f} of normal in 5 of last 15 min, other channels normal", f"Check cabling / grounding of {ch}.")
                        cls_override = "SENSOR"
            # --- STEP 1: drift against a fixed physics reference
            ip_n = ip_n + 1 if (not np.isnan(ipr[j]) and 0.04 < abs(ipr[j]) < 0.4) else 0     # >40 % = model failure, not a sensor
            if ip_n == 60 and not fire and sens_ok("ip", t, once=True):
                prev = ipr[j - 180] if j >= 180 and not np.isnan(ipr[j - 180]) else 0.0
                step = abs(ipr[j] - prev) > 0.7 * abs(ipr[j])                          # appeared within ~2 h -> step
                fire = ("SENSOR_CALIBRATION_SHIFT" if step else "SENSOR_DRIFT", 0.7,
                        f"motor current {ipr[j]*100:+.1f}% off the current-power line (healthy < 2.5%), {'sudden' if step else 'gradual'}",
                        "Verify current transducer against a clamp meter.")
            vib_ok = (np.isnan(bidx[j]) or bidx[j] < 0.25) and zv_abs[j] < k and za_abs[j] < k / 2
            bt_n = bt_n + 1 if (not np.isnan(btd[j]) and btd[j] > 6 and vib_ok) else 0
            if bt_n == 60 and not fire and sens_ok("bt", t, once=True):
                fire = ("SENSOR_DRIFT", 0.65, f"bearing temp {btd[j]:+.1f} C above its normal offset to the water, but vibration and bearing index normal", "Verify bearing temperature sensor.")
            if run[j] and bts[j] > 2.0 and not fire and sens_ok("btstuck", t, once=True):
                fire = ("SENSOR_STUCK", 0.8, f"bearing temperature unchanged for {bts[j]:.1f} h while running (healthy < 1 h)", "Check wireless sensor / battery.")
            if fire and not near:
                cls, ft = ("SENSOR" if fire[0].startswith("SENSOR") else "MACHINE"), fire[0]
                if ft == "IMPELLER_WEAR" and has_fh_col:           # let the full rule set name the head loss (air / cavitation / wear)
                    cls, ft, c, e2, act = diagnose2(g, j, k, ctl.get(a))
                    if ft == "UNKNOWN": ft, c, e2, act = fire[0], fire[1], fire[2], fire[3]
                    fire = (ft, c, e2, act)
                out.append({"asset_id": a, "alert_time_utc": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "event_class": cls,
                            "fault_type": fire[0], "confidence": fire[1], "evidence": fire[2], "recommended_action": fire[3]})
                ex.setdefault(a, []).append(t)
    return out
