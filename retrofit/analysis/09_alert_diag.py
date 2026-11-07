# SENTRY v1 diagnosis: alerts vs events (approximate the scorer's matching)
import sys

import pandas as pd

ROOT = r"."
p = pd.read_csv(ROOT + r"\build\predictions_sentry_v1_validation.csv", parse_dates=["alert_time_utc"])
ev = pd.read_csv(ROOT + r"\data\full\events_validation.csv", parse_dates=["onset_utc", "detectable_utc", "action_deadline_utc", "end_utc"])
for aid in sorted(p.asset_id.unique()):
    pa = p[p.asset_id == aid].sort_values("alert_time_utc")
    ea = ev[ev.asset_id == aid]
    print(f"\n===== {aid} =====")
    for a in pa.itertuples():
        # event window: start = max(onset, det-6h); end per rules
        matched = None
        for e in ea.itertuples():
            ws = max(e.onset_utc, (e.detectable_utc - pd.Timedelta("6h")))
            ee = e.end_utc if pd.notna(e.end_utc) else pa.alert_time_utc.max() + pd.Timedelta("1h")
            pad = pd.Timedelta("30min") if (e.fault_type in ("CAVITATION", "AIR_ENTRAINMENT")
                                            or e.event_class == "SENSOR") else pd.Timedelta(0)
            if ws <= a.alert_time_utc <= ee + pad:
                matched = f"{e.fault_type}(w [{str(ws)[11:16]} d{ (ws - pd.Timestamp(ws).floor('D')).total_seconds()/86400:.2f}..{(ee + pad).strftime('%m-%d %H:%M')}]"
                break
        tag = matched or "  FALSE/NO-MATCH"
        print(f"{a.alert_time_utc}  {a.event_class:7s} {a.fault_type:24s} conf {a.confidence:.2f} -> {tag}")

