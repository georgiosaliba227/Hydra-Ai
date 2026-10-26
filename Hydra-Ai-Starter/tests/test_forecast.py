import unittest
from ai.forecast import estimate

class ForecastTests(unittest.TestCase):
    def test_baseline(self):
        self.assertEqual(estimate(70).target_ml, 2100)

    def test_activity_increases_estimate(self):
        self.assertGreater(estimate(70, 60).target_ml, estimate(70).target_ml)

    def test_invalid_weight(self):
        with self.assertRaises(ValueError):
            estimate(-1)

if __name__ == "__main__":
    unittest.main()
