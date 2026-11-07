import csv
import time
import unittest
from collections import Counter
from pathlib import Path

from src.models import AlertPrediction
from src.severity import Severity, categorize_alert

REPO_ROOT = Path(__file__).resolve().parents[2]
FINE_TUNED_DIR = REPO_ROOT / "joice_physics_rules" / "dashboard_data_fine_tuned"


class AlertSeverityTests(unittest.TestCase):
    def test_unknown_is_low_confidence_even_at_high_confidence(self):
        self.assertEqual(
            categorize_alert("MACHINE", "UNKNOWN", 0.95),
            Severity.LOW_CONFIDENCE,
        )
        self.assertEqual(
            categorize_alert("SENSOR", "UNKNOWN", 0.15),
            Severity.LOW_CONFIDENCE,
        )

    def test_machine_severe_threshold_is_inclusive(self):
        self.assertEqual(categorize_alert("MACHINE", "BEARING_WEAR", 0.75), Severity.SEVERE)
        self.assertEqual(categorize_alert("MACHINE", "BEARING_WEAR", 0.74), Severity.MODERATE)

    def test_sensor_alerts_are_not_severe_from_confidence_alone(self):
        self.assertEqual(categorize_alert("SENSOR", "SENSOR_STUCK", 0.95), Severity.MODERATE)
        self.assertEqual(categorize_alert("SENSOR", "COMMUNICATION_LOSS", 0.95), Severity.MODERATE)

    def test_moderate_threshold_is_inclusive(self):
        self.assertEqual(categorize_alert("SENSOR", "SENSOR_DRIFT", 0.50), Severity.MODERATE)
        self.assertEqual(categorize_alert("MACHINE", "IMPELLER_WEAR", 0.50), Severity.MODERATE)
        self.assertEqual(categorize_alert("SENSOR", "SENSOR_DRIFT", 0.49), Severity.MINIMAL)
        self.assertEqual(categorize_alert("MACHINE", "IMPELLER_WEAR", 0.40), Severity.MINIMAL)

    def test_pydantic_computed_field_and_json_roundtrip_on_all_splits(self):
        splits = {
            "train": FINE_TUNED_DIR / "company_train" / "alerts.csv",
            "validation": FINE_TUNED_DIR / "company_validation" / "alerts.csv",
            "test": FINE_TUNED_DIR / "predictions_test.csv",
        }
        for split_name, csv_path in splits.items():
            self.assertTrue(csv_path.exists(), f"Missing {csv_path}")
            with csv_path.open(newline="", encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
            self.assertGreater(len(rows), 0, f"Empty alerts in {split_name}")

            counts = Counter()
            t0 = time.perf_counter()
            for r in rows:
                pred = AlertPrediction(
                    asset_id=r["asset_id"],
                    alert_time_utc=r["alert_time_utc"],
                    event_class=r["event_class"],
                    fault_type=r["fault_type"],
                    confidence=float(r["confidence"]),
                    evidence=r.get("evidence") or None,
                    recommended_action=r.get("recommended_action") or None,
                )
                dumped = pred.model_dump(mode="json")
                self.assertIn(dumped["severity"], {"SEVERE", "MODERATE", "MINIMAL", "LOW_CONFIDENCE"})
                restored = AlertPrediction(**dumped)
                self.assertEqual(restored.severity, pred.severity)
                counts[pred.severity.value] += 1
            dt_ms = (time.perf_counter() - t0) * 1000.0
            default_shown = counts["SEVERE"] + counts["MODERATE"]
            print(
                f"\n[Laya benchmark: {split_name:10s}] total={len(rows):2d} "
                f"SEVERE={counts['SEVERE']:2d} MODERATE={counts['MODERATE']:2d} "
                f"MINIMAL={counts['MINIMAL']:2d} LOW_CONFIDENCE={counts['LOW_CONFIDENCE']:2d} | "
                f"default_UI_shown={default_shown}/{len(rows)} ({100*default_shown/len(rows):.1f}%) | "
                f"{dt_ms:.2f} ms"
            )

    def test_laya_nuisance_suppression_benchmark(self):
        """Verify Laya suppresses MINIMAL (<0.50) and LOW_CONFIDENCE (UNKNOWN) alerts in default view."""
        synthetic_stream = (
            [("MACHINE", "BEARING_WEAR", 0.85)] * 12
            + [("MACHINE", "SUCTION_STRAINER_CLOGGING", 0.65)] * 10
            + [("SENSOR", "SENSOR_STUCK", 0.90)] * 6
            + [("MACHINE", "DISCHARGE_RESTRICTION", 0.32)] * 40
            + [("SENSOR", "SENSOR_NOISE_SPIKES", 0.18)] * 25
            + [("MACHINE", "UNKNOWN", 0.70)] * 7
        )
        counts = Counter(categorize_alert(ec, ft, conf).value for ec, ft, conf in synthetic_stream)
        self.assertEqual(counts["SEVERE"], 12)
        self.assertEqual(counts["MODERATE"], 16)
        self.assertEqual(counts["MINIMAL"], 65)
        self.assertEqual(counts["LOW_CONFIDENCE"], 7)
        suppressed = counts["MINIMAL"] + counts["LOW_CONFIDENCE"]
        shown = counts["SEVERE"] + counts["MODERATE"]
        print(
            f"\n[Laya benchmark: mixed_100 ] total={len(synthetic_stream):3d} "
            f"SEVERE={counts['SEVERE']:2d} MODERATE={counts['MODERATE']:2d} "
            f"MINIMAL={counts['MINIMAL']:2d} LOW_CONFIDENCE={counts['LOW_CONFIDENCE']:2d} | "
            f"default_UI_shown={shown}/{len(synthetic_stream)} ({100*suppressed/len(synthetic_stream):.1f}% nuisance suppressed)"
        )
        raw_ml = Path(r"C:\sentry-msi\pred\msi6350_train.csv")
        if raw_ml.exists():
            with raw_ml.open(newline="", encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
            ml_counts = Counter(
                categorize_alert(r["event_class"], r["fault_type"], float(r["confidence"])).value
                for r in rows
            )
            ml_supp = ml_counts["MINIMAL"] + ml_counts["LOW_CONFIDENCE"]
            ml_shown = ml_counts["SEVERE"] + ml_counts["MODERATE"]
            print(
                f"[Laya benchmark: msi6350_ml] total={len(rows):3d} "
                f"SEVERE={ml_counts['SEVERE']:2d} MODERATE={ml_counts['MODERATE']:2d} "
                f"MINIMAL={ml_counts['MINIMAL']:3d} LOW_CONFIDENCE={ml_counts['LOW_CONFIDENCE']:2d} | "
                f"default_UI_shown={ml_shown}/{len(rows)} ({100*ml_supp/len(rows):.1f}% nuisance suppressed)"
            )


if __name__ == "__main__":
    unittest.main()
