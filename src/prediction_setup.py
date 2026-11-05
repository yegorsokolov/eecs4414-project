"""Role D (RQ3): weekly cut-offs, candidate pairs, labels and train/val/test split.

Input: Role A's data/processed/edges.csv (columns source, target, timestamp,
sentiment) or a raw SNAP TSV. sentiment: -1 = negative, +1 = non-negative.

Definitions (match Section 2 of the report):
    cut-off T         weekly, first T = first link + 90 days, step 7 days
    training graph    G[T-90d, T)
    candidates        ordered pairs (u, v) with an edge u->v or v->u in G[T-90d, T)
    label             1 if a NEGATIVE edge u->v appears in G[T, T+7d)
    split             train: label window ends by 2016-01-01
                      val:   label window inside 2016
                      test:  label window starts on/after 2017-01-01
                      (a week whose label window crosses a boundary is dropped,
                       so no label ever leaks across splits)

Usage:
    python src/prediction_setup.py data/processed/edges.csv --out data/processed/rq3_summary.csv
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

LOOKBACK = pd.Timedelta(days=90)
HORIZON = pd.Timedelta(days=7)
STEP = pd.Timedelta(days=7)
VAL_START = pd.Timestamp("2016-01-01")
TEST_START = pd.Timestamp("2017-01-01")


ALIASES = {  # accepted column names -> canonical
    "src": ("source", "SOURCE_SUBREDDIT", "src"),
    "dst": ("target", "TARGET_SUBREDDIT", "dst"),
    "ts": ("timestamp", "TIMESTAMP", "ts"),
    "sign": ("sentiment", "LINK_SENTIMENT", "sign"),
}


def load_edges(path: str) -> pd.DataFrame:
    """Load Role A's data/processed/edges.csv (source,target,timestamp,sentiment,...)
    or a raw SNAP TSV (.tsv/.tsv.gz). Parquet also works."""
    p = str(path)
    if p.endswith(".parquet"):
        df = pd.read_parquet(p)
    else:
        sep = "\t" if (p.endswith(".tsv") or p.endswith(".tsv.gz")) else ","
        header = pd.read_csv(p, sep=sep, nrows=0).columns
        wanted = [n for names in ALIASES.values() for n in names if n in header]
        df = pd.read_csv(p, sep=sep, usecols=wanted)  # skip post_id, provenance, PROPERTIES
    rename = {}
    for canon, names in ALIASES.items():
        hit = next((n for n in names if n in df.columns), None)
        if hit is None:
            raise ValueError(f"{path}: no column for {canon!r}; looked for {names}")
        rename[hit] = canon
    df = df[list(rename)].rename(columns=rename)
    df["ts"] = pd.to_datetime(df["ts"])
    df = df[df["src"] != df["dst"]]
    return df.sort_values("ts", kind="stable").reset_index(drop=True)


def encode(df: pd.DataFrame) -> pd.DataFrame:
    """Map subreddit names to integer ids so pair keys are fast int64s."""
    names = pd.unique(np.concatenate([df["src"].to_numpy(), df["dst"].to_numpy()]))
    ids = pd.Series(np.arange(len(names)), index=names)
    out = df.copy()
    out["u"] = ids[df["src"]].to_numpy()
    out["v"] = ids[df["dst"]].to_numpy()
    out["neg"] = (df["sign"] < 0).to_numpy()
    out.attrs["n_nodes"] = len(names)
    return out


def weekly_cutoffs(first: pd.Timestamp, last: pd.Timestamp) -> list[pd.Timestamp]:
    """T = first + 90d, +7d, ... while the label window [T, T+7d) fits in the data."""
    cuts, t = [], first + LOOKBACK
    while t + HORIZON <= last + pd.Timedelta(seconds=1):
        cuts.append(t)
        t += STEP
    return cuts


def split_of(t: pd.Timestamp) -> str | None:
    """Split for cut-off T, or None if its label window crosses a boundary."""
    end = t + HORIZON
    if end <= VAL_START:
        return "train"
    if t >= VAL_START and end <= TEST_START:
        return "val"
    if t >= TEST_START:
        return "test"
    return None


def _key(a: np.ndarray, b: np.ndarray, n: int) -> np.ndarray:
    return a.astype(np.int64) * n + b.astype(np.int64)


def candidates_and_labels(e: pd.DataFrame, t: pd.Timestamp, n: int):
    """Candidates and labels for one cut-off T.

    Returns (candidate_keys, labels, n_neg_pairs, n_covered): the sorted int64 pair
    keys, a boolean label per candidate, the number of distinct ordered pairs with a
    negative link in [T, T+7d), and how many of those pairs are candidates.
    """
    ts = e["ts"].to_numpy()
    lo, mid, hi = (np.searchsorted(ts, np.datetime64(x), side="left") for x in (t - LOOKBACK, t, t + HORIZON))
    past, fut = e.iloc[lo:mid], e.iloc[mid:hi]
    u, v = past["u"].to_numpy(), past["v"].to_numpy()
    cand = np.unique(np.concatenate([_key(u, v, n), _key(v, u, n)]))  # either direction -> both ordered pairs
    fneg = fut[fut["neg"]]
    pos = np.unique(_key(fneg["u"].to_numpy(), fneg["v"].to_numpy(), n))
    labels = np.isin(cand, pos)
    return cand, labels, len(pos), int(labels.sum())


def build_summary(e: pd.DataFrame) -> pd.DataFrame:
    """One row per split: weeks, candidates, positives, positive rate, coverage."""
    n = e.attrs["n_nodes"]
    rows = []
    for t in weekly_cutoffs(e["ts"].iloc[0], e["ts"].iloc[-1]):
        s = split_of(t)
        if s is None:
            continue
        cand, labels, n_pos_pairs, n_covered = candidates_and_labels(e, t, n)
        rows.append((s, t, len(cand), int(labels.sum()), n_pos_pairs))
    wk = pd.DataFrame(rows, columns=["split", "T", "candidates", "positives", "neg_pairs_in_horizon"])
    g = wk.groupby("split").agg(
        weeks=("T", "size"),
        candidates=("candidates", "sum"),
        positives=("positives", "sum"),
        neg_pairs=("neg_pairs_in_horizon", "sum"),
    )
    g["positive_rate_pct"] = 100 * g["positives"] / g["candidates"]
    g["avg_candidates_per_week"] = g["candidates"] / g["weeks"]
    # share of all new negative (u,v) pairs that were reachable as candidates (recall ceiling)
    g["coverage_pct"] = 100 * g["positives"] / g["neg_pairs"]
    return g.reindex(["train", "val", "test"]).drop(columns="neg_pairs")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("edges")
    ap.add_argument("--out", default="data/processed/rq3_summary.csv")
    a = ap.parse_args()
    e = encode(load_edges(a.edges))
    summ = build_summary(e)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    summ.to_csv(a.out)
    pd.set_option("display.float_format", "{:,.3f}".format)
    pd.set_option("display.width", 200)
    print(summ.to_string())


if __name__ == "__main__":
    main()
