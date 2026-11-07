import unittest

from src.severity import Severity, categorize_alert


class AlertSeverityTests(unittest.TestCase):
    def test_unknown_is_low_confidence_even_at_high_confidence(self):
        self.assertEqual(
            categorize_alert("MACHINE", "UNKNOWN", 0.95),
            Severity.LOW_CONFIDENCE,
        )

    def test_machine_severe_threshold_is_inclusive(self):
        self.assertEqual(categorize_alert("MACHINE", "BEARING_WEAR", 0.75), Severity.SEVERE)
        self.assertEqual(categorize_alert("MACHINE", "BEARING_WEAR", 0.74), Severity.MODERATE)

    def test_sensor_alerts_are_not_severe_from_confidence_alone(self):
        self.assertEqual(categorize_alert("SENSOR", "SENSOR_STUCK", 0.95), Severity.MODERATE)

    def test_moderate_threshold_is_inclusive(self):
        self.assertEqual(categorize_alert("SENSOR", "SENSOR_DRIFT", 0.50), Severity.MODERATE)
        self.assertEqual(categorize_alert("SENSOR", "SENSOR_DRIFT", 0.49), Severity.MINIMAL)


if __name__ == "__main__":
    unittest.main()
