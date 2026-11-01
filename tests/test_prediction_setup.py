import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import prediction_setup as ps  # noqa: E402


def make(rows):
    df = pd.DataFrame(rows, columns=["src", "dst", "ts", "sign"])
    df["ts"] = pd.to_datetime(df["ts"])
    return ps.encode(df.sort_values("ts").reset_index(drop=True))


def test_first_cutoff_is_90_days_after_first_link():
    cuts = ps.weekly_cutoffs(pd.Timestamp("2014-01-01"), pd.Timestamp("2014-06-01"))
    assert cuts[0] == pd.Timestamp("2014-04-01")
    assert cuts[1] - cuts[0] == pd.Timedelta(days=7)


def test_split_boundaries_and_dropped_weeks():
    assert ps.split_of(pd.Timestamp("2015-06-01")) == "train"
    assert ps.split_of(pd.Timestamp("2015-12-28")) is None      # label window crosses 2016-01-01
    assert ps.split_of(pd.Timestamp("2016-06-01")) == "val"
    assert ps.split_of(pd.Timestamp("2016-12-28")) is None      # crosses 2017-01-01
    assert ps.split_of(pd.Timestamp("2017-02-01")) == "test"


def test_candidates_both_directions_and_label():
    # a->b link 10 days before T; negative b->a... label is for ordered pair (u, v)
    rows = [
        ("a", "b", "2014-03-22", 1),    # past link a->b  -> candidates (a,b) and (b,a)
        ("a", "c", "2013-12-25", 1),    # older than 90 days before T -> not a candidate
        ("a", "b", "2014-04-03", -1),   # negative a->b inside [T, T+7d)  -> label (a,b)=1
        ("b", "a", "2014-04-04", 1),    # non-negative b->a -> label (b,a)=0
    ]
    e = make(rows)
    T = pd.Timestamp("2014-04-01")
    cand, labels, n_pos_pairs, n_covered = ps.candidates_and_labels(e, T, e.attrs["n_nodes"])
    assert len(cand) == 2
    assert labels.sum() == 1 and n_pos_pairs == 1 and n_covered == 1


def test_negative_link_on_unseen_pair_is_not_covered():
    rows = [
        ("a", "b", "2014-03-22", 1),
        ("x", "y", "2014-04-02", -1),   # brand-new pair: positive event, but not a candidate
    ]
    e = make(rows)
    cand, labels, n_pos_pairs, n_covered = ps.candidates_and_labels(e, pd.Timestamp("2014-04-01"), e.attrs["n_nodes"])
    assert labels.sum() == 0 and n_pos_pairs == 1 and n_covered == 0


def test_label_window_is_half_open():
    rows = [("a", "b", "2014-03-22", 1), ("a", "b", "2014-04-08", -1)]  # exactly T+7d -> excluded
    e = make(rows)
    _, labels, n_pos_pairs, _ = ps.candidates_and_labels(e, pd.Timestamp("2014-04-01"), e.attrs["n_nodes"])
    assert labels.sum() == 0 and n_pos_pairs == 0


def test_no_future_information_in_candidates():
    rows = [("a", "b", "2014-04-02", -1)]  # after T: must not create a candidate
    e = make(rows)
    cand, *_ = ps.candidates_and_labels(e, pd.Timestamp("2014-04-01"), e.attrs["n_nodes"])
    assert len(cand) == 0
