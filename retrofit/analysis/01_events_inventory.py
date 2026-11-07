# Stage 1: Event inventory & timelines from events_train.csv / events_validation.csv
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT + r"\data\full"

tr = pd.read_csv(DATA + r"\events_train.csv", parse_dates=["onset_utc", "detectable_utc", "action_deadline_utc", "end_utc"])
va = pd.read_csv(DATA + r"\events_validation.csv", parse_dates=["onset_utc", "detectable_utc", "action_deadline_utc", "end_utc"])
assets = pd.read_csv(DATA + r"\assets.csv")

ev = pd.concat([tr.assign(split="train"), va.assign(split="validation")], ignore_index=True)

print("=" * 100)
print("EVENT COUNTS by split / class / fault_type (with observable flag)")
print("=" * 100)
cnt = ev.groupby(["split", "event_class", "fault_type", "observable"]).size().reset_index(name="n")
print(cnt.to_string(index=False))

print()
print("=" * 100)
print("FULL EVENT TABLE (times as day+HH:MM offsets relative to each asset window start)")
print("=" * 100)
assets["window_start_utc"] = pd.to_datetime(assets["window_start_utc"])
off = ev.merge(assets[["asset_id", "window_start_utc", "instrumentation_tier", "control", "profile", "split"]],
               on="asset_id", suffixes=("", "_asset"))


def fmt(t, base):
    if pd.isna(t):
        return "-"
    d = (t - base).total_seconds() / 86400.0
    return f"{d:.2f}d"


rows = []
for _, r in off.iterrows():
    b = r["window_start_utc"]
    rows.append({
        "split": r["split"], "asset": r["asset_id"], "tier": r["instrumentation_tier"],
        "class": r["event_class"], "fault": r["fault_type"],
        "onset": fmt(r["onset_utc"], b),
        "detect": fmt(r["detectable_utc"], b),
        "deadline": fmt(r["action_deadline_utc"], b),
        "end": fmt(r["end_utc"], b),
        "obs": "Y" if r["observable"] else "N",
        "sev": r["severity"],
        "evidence(head)": str(r["evidence_channels"])[:40],
        "note": str(r["root_cause_event_id"])[:30],
    })
tbl = pd.DataFrame(rows)
pd.set_option("display.width", 250)
print(tbl.sort_values(["split", "asset", "onset"]).to_string(index=False))

print()
print("=" * 100)
print("SIGNAL RICHNESS: which channels each fault type needed (count of scored, observable events)")
print("=" * 100)
for _, r in ev.iterrows():
    lead = ""
    if pd.notna(r["action_deadline_utc"]) and pd.notna(r["detectable_utc"]):
        lead = f" lead={((r['action_deadline_utc'] - r['detectable_utc']).total_seconds()/3600):.1f}h"
    print(f"{r['asset_id']:8s} {r['fault_type']:24s} obs={str(r['observable']):5s} "
          f"evidence={r['evidence_channels']}{lead}")

