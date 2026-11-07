# Full train/v alert-vs-event matcher (mirrors scorer semantics closely)
import pandas as pd

MODE = pd.DataFrame()


def match_all(pred_csv, events_csv, split_name):
    p = pd.read_csv(pred_csv, parse_dates=["alert_time_utc"])
    ev = pd.read_csv(events_csv, parse_dates=["onset_utc", "detectable_utc", "action_deadline_utc", "end_utc"])
    print(f"\n===== {split_name}: events matched detail =====")
    for e in ev.itertuples():
        ws = max(e.onset_utc, (e.detectable_utc - pd.Timedelta("6h")))
        pad = pd.Timedelta("30min") if (e.fault_type in ("CAVITATION", "AIR_ENTRAINMENT") or e.event_class == "SENSOR") else pd.Timedelta(0)
        ee = (e.end_utc if pd.notna(e.end_utc) else p.alert_time_utc.max() + pd.Timedelta("1h")) + pad
        pa = p[(p.asset_id == e.asset_id) & (p.alert_time_utc >= ws) & (p.alert_time_utc <= ee)]
        first = pa.iloc[0] if len(pa) else None
        if first is None:
            print(f"  MISS   {e.event_id:16s} {e.fault_type:24s} [{str(ws)[:16]} .. {str(ee)[:16]}]")
            continue
        repeat_excess = max(0, len(pa) - 2) if len(pa) > 1 else 0
        lead = ""
        if pd.notna(e.action_deadline_utc):
            lead = f" (dl in +{(e.action_deadline_utc - first.alert_time_utc).total_seconds()/3600:.1f}h)"
        print(f"  DETECT {e.event_id:16s} {e.fault_type:24s} alert={str(first.alert_time_utc)[:16]} '{first.fault_type}'"
              f" matches_truth={first.fault_type == e.fault_type}{lead}" + (f" REPEATS={len(pa)-1}" if len(pa) > 1 else ""))
    # unmatched alerts
    print("----- unmatched (false) alerts -----")
    for a in p.itertuples():
        in_any = False
        for e in ev[ev.asset_id == a.asset_id].itertuples():
            ws = max(e.onset_utc, (e.detectable_utc - pd.Timedelta("6h")))
            pad = pd.Timedelta("30min") if (e.fault_type in ("CAVITATION", "AIR_ENTRAINMENT") or e.event_class == "SENSOR") else pd.Timedelta(0)
            ee = (e.end_utc if pd.notna(e.end_utc) else a.alert_time_utc) + pad
            if ws <= a.alert_time_utc <= ee:
                in_any = True
                break
        if not in_any:
            print(f"  FALSE  {a.asset_id} {a.alert_time_utc} {a.fault_type:24s} | {a.evidence[:80]}")


match_all(r"build\predictions_sentry_v6_train.csv", r"data\full\events_train.csv", "train")

