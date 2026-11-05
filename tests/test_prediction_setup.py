"""Tests for Role D (RQ3) prediction setup: cut-offs, candidates, labels, split.

Run with the team command:  python -m unittest discover -s tests -v
"""
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src import prediction_setup as ps


def make(rows):
    """Build an encoded edge table from (src, dst, timestamp, sign) rows."""
    df = pd.DataFrame(rows, columns=["src", "dst", "ts", "sign"])
    df["ts"] = pd.to_datetime(df["ts"])
    return ps.encode(df.sort_values("ts").reset_index(drop=True))


def run(rows, cutoff):
    e = make(rows)
    return ps.candidates_and_labels(e, pd.Timestamp(cutoff), e.attrs["n_nodes"])


class CutoffAndSplitTests(unittest.TestCase):
    def test_first_cutoff_is_90_days_after_first_link(self):
        cuts = ps.weekly_cutoffs(pd.Timestamp("2014-01-01"), pd.Timestamp("2014-06-01"))
        self.assertEqual(cuts[0], pd.Timestamp("2014-04-01"))
        self.assertEqual(cuts[1] - cuts[0], pd.Timedelta(days=7))

    def test_last_label_window_fits_in_the_data(self):
        last = pd.Timestamp("2014-06-01")
        cuts = ps.weekly_cutoffs(pd.Timestamp("2014-01-01"), last)
        self.assertLessEqual(cuts[-1] + ps.HORIZON, last + pd.Timedelta(seconds=1))

    def test_split_boundaries_and_dropped_weeks(self):
        self.assertEqual(ps.split_of(pd.Timestamp("2015-06-01")), "train")
        self.assertIsNone(ps.split_of(pd.Timestamp("2015-12-28")))  # label window crosses 2016-01-01
        self.assertEqual(ps.split_of(pd.Timestamp("2016-06-01")), "val")
        self.assertIsNone(ps.split_of(pd.Timestamp("2016-12-28")))  # crosses 2017-01-01
        self.assertEqual(ps.split_of(pd.Timestamp("2017-02-01")), "test")


class CandidateAndLabelTests(unittest.TestCase):
    def test_candidates_both_directions_and_label(self):
        rows = [
            ("a", "b", "2014-03-22", 1),   # past link a->b  -> candidates (a,b) and (b,a)
            ("a", "c", "2013-12-25", 1),   # older than 90 days before T -> not a candidate
            ("a", "b", "2014-04-03", -1),  # negative a->b inside [T, T+7d) -> label (a,b)=1
            ("b", "a", "2014-04-04", 1),   # non-negative b->a -> label (b,a)=0
        ]
        cand, labels, n_pos_pairs, n_covered = run(rows, "2014-04-01")
        self.assertEqual(len(cand), 2)
        self.assertEqual((int(labels.sum()), n_pos_pairs, n_covered), (1, 1, 1))

    def test_negative_link_on_unseen_pair_is_not_covered(self):
        rows = [("a", "b", "2014-03-22", 1), ("x", "y", "2014-04-02", -1)]
        _, labels, n_pos_pairs, n_covered = run(rows, "2014-04-01")
        self.assertEqual((int(labels.sum()), n_pos_pairs, n_covered), (0, 1, 0))

    def test_label_window_is_half_open(self):
        rows = [("a", "b", "2014-03-22", 1), ("a", "b", "2014-04-08", -1)]  # exactly T+7d -> excluded
        _, labels, n_pos_pairs, _ = run(rows, "2014-04-01")
        self.assertEqual((int(labels.sum()), n_pos_pairs), (0, 0))

    def test_no_future_information_in_candidates(self):
        cand, *_ = run([("a", "b", "2014-04-02", -1)], "2014-04-01")  # after T
        self.assertEqual(len(cand), 0)


class LoadAndSummaryTests(unittest.TestCase):
    def test_loads_role_a_edges_csv_columns(self):
        text = ("event_id,source,target,post_id,timestamp,sentiment,provenance\n"
                "0,a,b,p1,2014-01-01 00:00:00,1,title\n"
                "1,b,a,p2,2014-01-02 00:00:00,-1,body\n"
                "2,c,c,p3,2014-01-03 00:00:00,1,title\n")  # self-link is dropped
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "edges.csv"
            path.write_text(text, encoding="utf-8")
            df = ps.load_edges(str(path))
        self.assertEqual(list(df.columns), ["src", "dst", "ts", "sign"])
        self.assertEqual(len(df), 2)

    def test_summary_counts_on_tiny_network(self):
        # in each split: a non-negative b->a link, then a negative a->b a week later
        rows = [("a", "b", "2014-01-01", 1), ("a", "b", "2017-04-30", 1)]
        for day in ("2014-06-10", "2016-06-10", "2017-02-10"):
            d = pd.Timestamp(day)
            week_before = (d - pd.Timedelta(days=7)).strftime("%Y-%m-%d")
            rows += [("b", "a", week_before, 1), ("a", "b", day, -1)]
        summ = ps.build_summary(make(rows))
        self.assertEqual(list(summ.index), ["train", "val", "test"])
        self.assertEqual(list(summ["positives"]), [1, 1, 1])
        self.assertEqual(list(summ["coverage_pct"]), [100.0, 100.0, 100.0])


if __name__ == "__main__":
    unittest.main()
