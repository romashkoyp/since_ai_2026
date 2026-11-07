# Stage 4b: what does B1 miss / misdiagnose on validation
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ev = pd.read_csv(ROOT + r"\data\full\events_validation.csv",
                 parse_dates=["onset_utc", "detectable_utc", "action_deadline_utc", "end_utc"])
p = pd.read_csv(ROOT + r"\baselines\results\predictions_B1_mode_aware_z_validation.csv", parse_dates=["alert_time_utc"])

print("--- validation events (9 scored) vs B1 alert stream ---")
for e in ev.itertuples():
    pa = p[p.asset_id == e.asset_id]
    t_end = e.end_utc if pd.notna(e.end_utc) else pa.alert_time_utc.max()
    near = pa[(pa.alert_time_utc >= e.onset_utc - pd.Timedelta("7h")) & (pa.alert_time_utc <= t_end)]
    names = sorted(set(near.fault_type)) if len(near) else []
    t1 = near.alert_time_utc.min() if len(near) else None
    lead = "" if t1 is None or pd.isna(e.action_deadline_utc) else f"  lead={(e.action_deadline_utc - t1).total_seconds()/3600:.1f}h"
    print(f"{e.event_id:14s} {e.asset_id} {e.fault_type:24s} det={str(e.detectable_utc)[:16]:<16s} "
          f"dl={str(e.action_deadline_utc)[:16]:<16s} -> B1: first={str(t1) if t1 is not None else '-':<16s} guesses={names}{lead}")

print()
print("--- B1 alerts matched / unmatched ---")
for a in p.itertuples():
    e = ev[(ev.asset_id == a.asset_id) & (ev.onset_utc - pd.Timedelta("7h") <= a.alert_time_utc) &
           ((ev.end_utc >= a.alert_time_utc) | ev.end_utc.isna())]
    tag = "matched " + e.fault_type.iloc[0] if len(e) else "NO EVENT (false/nuisance)"
    print(f"{a.asset_id} {str(a.alert_time_utc)[:16]} {a.event_class:8s} {a.fault_type:22s} conf={a.confidence:.2f}  {tag}")

