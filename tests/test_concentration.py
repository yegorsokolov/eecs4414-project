"""Tests for Role B (RQ1) concentration analysis on small hand-checked networks.

Run with the team command:  python -m unittest discover -s tests -v
"""
import unittest

import pandas as pd

from src import concentration as rq1


def edges(rows):
    """Build an edge table from (src, dst, sign) rows with increasing timestamps."""
    df = pd.DataFrame(rows, columns=["src", "dst", "sign"])
    df["ts"] = pd.date_range("2014-01-01", periods=len(df), freq="h")
    return df


class DegreeTests(unittest.TestCase):
    def test_degrees_count_parallel_edges(self):
        df = edges([("a", "b", 1), ("a", "b", -1), ("b", "c", 1)])
        deg = rq1.degrees(df)
        self.assertEqual(deg.loc["a", "out"], 2)
        self.assertEqual(deg.loc["b", "total"], 3)
        self.assertEqual(deg.loc["b", "neg_in"], 1)
        self.assertAlmostEqual(deg.loc["a", "neg_fraction"], 0.5)


class ConcentrationTests(unittest.TestCase):
    def test_r_k_matches_hand_calculation(self):
        # hub h has degree 6 and is the top 1% (ceil(0.01 * 5) = 1 node)
        rows = [("h", "a", -1), ("h", "b", -1), ("h", "c", 1), ("a", "h", 1),
                ("b", "h", 1), ("c", "h", 1), ("a", "b", 1), ("c", "d", -1)]
        df = edges(rows)
        conc = rq1.concentration(df, rq1.degrees(df), ks=(1,)).iloc[0]
        self.assertEqual(conc["nodes"], 1)
        self.assertAlmostEqual(conc["share_all_links"], 6 / 8)
        self.assertAlmostEqual(conc["share_negative_links"], 2 / 3)
        self.assertAlmostEqual(conc["R_k"], (2 / 3) / (6 / 8))

    def test_ties_are_broken_by_name(self):
        df = edges([("b", "x", -1), ("a", "y", 1)])  # a, b, x, y all have degree 1
        conc = rq1.concentration(df, rq1.degrees(df), ks=(25,)).iloc[0]  # top 1 of 4 nodes
        self.assertAlmostEqual(conc["share_all_links"], 0.5)
        self.assertAlmostEqual(conc["share_negative_links"], 0.0)  # "a" chosen, not "b"


class ReciprocityTests(unittest.TestCase):
    def test_reciprocity_by_event_and_by_pair(self):
        rows = [("a", "b", -1), ("a", "b", -1), ("b", "a", -1), ("a", "c", -1), ("c", "a", 1)]
        rec = rq1.reciprocity(edges(rows))
        self.assertAlmostEqual(rec["events_reciprocated"], 3 / 4)       # c->a is not negative
        self.assertAlmostEqual(rec["distinct_pairs_reciprocated"], 2 / 3)
        self.assertEqual(rec["distinct_negative_pairs"], 3)


class MonthlyTests(unittest.TestCase):
    def test_monthly_share(self):
        df = pd.DataFrame({"src": ["a", "a", "b"], "dst": ["b", "c", "a"], "sign": [-1, 1, 1],
                           "ts": pd.to_datetime(["2014-01-05", "2014-01-20", "2014-02-01"])})
        mon = rq1.monthly(df).set_index("month")
        self.assertEqual(mon.loc["2014-01", "negative_links"], 1)
        self.assertAlmostEqual(mon.loc["2014-01", "negative_share_pct"], 50.0)
        self.assertEqual(mon.loc["2014-02", "negative_links"], 0)


if __name__ == "__main__":
    unittest.main()
