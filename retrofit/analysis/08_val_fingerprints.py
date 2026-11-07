# Per-event block-timeline fingerprints for an asset list (reusable)
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
from sentry.regime import build_residuals

DATA = r"data\full"
assets = pd.read_csv(DATA + r"\assets.csv")
feats = pd.read_parquet(DATA + r"\features_1min.parquet")


def dump(aid_list, ev_df, fname):
    ev = pd.read_csv(ev_df, parse_dates=["onset_utc", "detectable_utc", "end_utc"])
    lines = []
    for aid in aid_list:
        a = assets[assets.asset_id == aid].iloc[0]
        f = feats[feats.asset_id == aid].sort_values("window_start_utc").set_index("window_start_utc")
        t0 = f.index[0]
        chans = [c.replace("__mean", "") for c in f.columns if c.endswith("__mean")]
        chan_set = set(chans)
        r = build_residuals(f, chans, a, ffill_sparse=90)
        lines.append(f"\n=== {aid} (tier {a.instrumentation_tier}, control {a.control}) ===")
        for e in ev[ev.asset_id == aid].itertuples():
            ev_ch = [c.strip() for c in str(e.evidence_channels).split(",") if c.strip() in chan_set]
            lo = max((e.onset_utc if pd.notna(e.onset_utc) else t0) - pd.Timedelta("12h"), t0)
            hi = e.end_utc if pd.notna(e.end_utc) else f.index[-1]
            lines.append(f"\n{e.event_id} {e.fault_type} [{(e.onset_utc - t0).total_seconds()/86400:.2f}d] det={e.detectable_utc.strftime('%d/%H:%M')} ev={ev_ch}")
            runv = ((f["operating_mode"] == "RUNNING") & (f["running_fraction"] > 0.9) & (f["rows"] >= 55)).values
            for st in pd.date_range(lo, hi, freq="6h"):
                m = (f.index >= st) & (f.index < st + pd.Timedelta("6h"))
                sel = m & runv
                names = ev_ch if ev_ch else chans[:0]
                use = ev_ch if ev_ch else [c for c in chans][:6]
                parts = []
                for c in use:
                    v = r[f"{c}__z"].values[sel]
                    if len(v) > 3:
                        parts.append(f"{c}={np.median(v):+.1f}")
                lines.append(f"   [{(st - t0).total_seconds()/86400:04.2f}d] " + ("  ".join(parts) if parts else "(no data)"))
    with open(fname, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print("wrote", fname)


if __name__ == "__main__":
    dump(["PUMP-01", "PUMP-02", "PUMP-03", "PUMP-04", "PUMP-06", "PUMP-07"],
         DATA + r"\events_train.csv", r"analysis\08_out_train.txt")
    dump(["PUMP-08", "PUMP-09"],
         DATA + r"\events_validation.csv", r"analysis\08_out.txt")

