"""The swappable ML part. A model is a folder:
    models/<version>/diagnostician.joblib   (from train_diagnostician.py)
    models/<version>/calibrator.joblib      (from integrate_hybrid.py)
    models/<version>/metadata.json          (written by scripts/export_model.py)
"""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import pandas as pd

from .config import ENGINE_FEATURE_VERSION
from .features import make_X


class ModelVersionError(RuntimeError):
    pass


class HybridModel:
    def __init__(self, folder: str | Path, check_version: bool = True):
        self.folder = Path(folder)
        meta_file = self.folder / "metadata.json"
        self.metadata = json.loads(meta_file.read_text()) if meta_file.exists() else {}
        if check_version and self.metadata.get("feature_version") != ENGINE_FEATURE_VERSION:
            raise ModelVersionError(
                f"model in {self.folder} was built for features '{self.metadata.get('feature_version')}', "
                f"engine computes '{ENGINE_FEATURE_VERSION}'. Retrain/export the model or update the engine.")
        bundle = joblib.load(self.folder / "diagnostician.joblib")
        self.model, self.columns = bundle["model"], bundle["columns"]
        self.classes = list(self.model.classes_)
        cal = self.folder / "calibrator.joblib"
        self.calibrator = joblib.load(cal) if cal.exists() else None

    @property
    def version(self) -> str:
        return self.metadata.get("model_version", self.folder.name)

    def info(self) -> dict:
        return {"model_version": self.version, "folder": str(self.folder), "classes": self.classes,
                "n_features": len(self.columns), "calibrated": self.calibrator is not None, **self.metadata}

    def diagnose(self, feats: pd.DataFrame) -> pd.DataFrame:
        """feats: one row per alert (output of features_at). Returns ml_type, ml_raw_conf, ml_conf (calibrated)."""
        if feats.empty:
            return pd.DataFrame(columns=["ml_type", "ml_raw_conf", "ml_conf"])
        P = pd.DataFrame(self.model.predict_proba(make_X(feats, self.columns)), index=feats.index, columns=self.classes)
        raw = P.max(axis=1)
        cal = pd.Series(self.calibrator.predict(raw.values), index=feats.index) if self.calibrator is not None else raw
        return pd.DataFrame({"ml_type": P.idxmax(axis=1), "ml_raw_conf": raw.round(4), "ml_conf": cal.round(4)})
