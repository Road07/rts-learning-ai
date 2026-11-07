import unittest
from profile_model_speed import distribution
class ProfileStats(unittest.TestCase):
    def test_empty_is_missing_not_zero_latency(self):
        row=distribution([]);self.assertEqual(row['n'],0);self.assertIsNone(row['mean'])
    def test_latency_statistics_preserve_outliers(self):
        row=distribution([1,2,3,4,5,100]);self.assertEqual(row['sum'],115);self.assertAlmostEqual(row['p95'],76.25)
    def test_single_sample(self):
        row=distribution([7]);self.assertEqual(row['mean'],7);self.assertEqual(row['p95'],7)
if __name__=='__main__':unittest.main()
