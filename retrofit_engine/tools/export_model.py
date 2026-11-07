"""Copy the trained hybrid from the training folder into retrofit_engine/model/.

Run from your FastAPI project folder (the one that contains retrofit_engine/):
    python -m retrofit_engine.tools.export_model --training "C:/.../RETROFIT_AI_PARTICIPANTS_2026" --version hybrid-v3-001
Takes build/models/diagnostician.joblib (train_diagnostician.py) and build/integration/calibrator.joblib
(integrate_hybrid.py).
"""
import argparse, json, shutil, sys
from datetime import datetime, timezone
from pathlib import Path

from ..config import ENGINE_FEATURE_VERSION, MIN_CONF, PHYSICS_VERSION, RULE_PRIORITY

p = argparse.ArgumentParser()
p.add_argument("--training", required=True)
p.add_argument("--version", required=True)
p.add_argument("--note", default="")
a = p.parse_args()
src = Path(a.training) / "build"
mf, cf = src / "models" / "diagnostician.joblib", src / "integration" / "calibrator.joblib"
if not mf.exists():
    sys.exit(f"not found: {mf} (run train_diagnostician.py first)")
dst = Path(__file__).resolve().parents[1] / "model"
dst.mkdir(exist_ok=True)
shutil.copy2(mf, dst / "diagnostician.joblib")
if cf.exists():
    shutil.copy2(cf, dst / "calibrator.joblib")
else:
    print("warning: no calibrator (run integrate_hybrid.py first); confidences will be uncalibrated")
meta = {"model_version": a.version, "feature_version": ENGINE_FEATURE_VERSION, "physics_version": PHYSICS_VERSION,
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "min_conf": MIN_CONF,
        "rule_priority": sorted(RULE_PRIORITY), "note": a.note}
(dst / "metadata.json").write_text(json.dumps(meta, indent=2))
print(f"model '{a.version}' installed in {dst}")
