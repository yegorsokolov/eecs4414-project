"""Count follow-up patterns between negative Reddit hyperlink events."""

import argparse
import csv
import gzip
import json
import time
from bisect import bisect_right
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

REQUIRED_COLUMNS = {"SOURCE_SUBREDDIT", "TARGET_SUBREDDIT", "TIMESTAMP", "LINK_SENTIMENT"}
# Role A's data/processed/edges.csv uses these names instead (comma-separated).
PROCESSED_COLUMNS = {"source": "SOURCE_SUBREDDIT", "target": "TARGET_SUBREDDIT",
                     "timestamp": "TIMESTAMP", "sentiment": "LINK_SENTIMENT"}
PATTERNS = ("reciprocal", "repeated", "outward", "converging", "chain")


def load_negative_events(path):
    """Read a raw SNAP .tsv/.tsv.gz file or Role A's edges.csv and return its
    negative events as tuples.

    Each event is (source, target, timestamp). Repeated events are kept. Rows with
    label 1 are skipped. A negative self-link raises ValueError because the
    pattern definitions assume source != target.
    """
    path = Path(path)
    opener = gzip.open if path.suffix == ".gz" else open
    events = []
    with opener(path, "rt", encoding="utf-8-sig", newline="") as stream:
        header = stream.readline()
        stream.seek(0)
        delimiter = "," if header.count(",") > header.count("\t") else "\t"
        reader = csv.DictReader(stream, delimiter=delimiter)
        if delimiter == "," and set(PROCESSED_COLUMNS) <= set(reader.fieldnames or []):
            reader.fieldnames = [PROCESSED_COLUMNS.get(c, c) for c in reader.fieldnames]
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Missing columns: {', '.join(sorted(missing))}")
        for line, row in enumerate(reader, start=2):
            try:
                source = row["SOURCE_SUBREDDIT"].strip()
                target = row["TARGET_SUBREDDIT"].strip()
                if not source or not target:
                    raise ValueError("subreddit names must be nonempty")
                sentiment = int(row["LINK_SENTIMENT"])
                if sentiment not in {-1, 1}:
                    raise ValueError("label must be -1 or 1")
                timestamp = datetime.strptime(row["TIMESTAMP"], "%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError, AttributeError) as exc:
                raise ValueError(f"Invalid row {line}: {exc}") from exc
            if sentiment != -1:
                continue
            if source == target:
                raise ValueError(
                    f"Negative self-link on row {line} ({source}); "
                    "the pattern definitions assume source != target")
            events.append((source, target, timestamp))
    return events


def classify_pair(first, second):
    """Name the pattern that second follows first, or None if it matches none.

    Events are (source, target, timestamp). Only the subreddits are compared;
    the time window is checked by the callers.
    """
    u, v, _ = first
    x, y, _ = second
    if x == v and y == u:
        return "reciprocal"
    if x == u and y == v:
        return "repeated"
    if x == u and y not in (u, v):
        return "outward"
    if x not in (u, v) and y == v:
        return "converging"
    if x == v and y not in (u, v):
        return "chain"
    return None


def empty_result():
    """Return a pattern table with every count set to zero."""
    return {name: {"pairs": 0, "distinct_followups": 0} for name in PATTERNS}


def count_patterns(events, deltas):
    """Count the five patterns for each window length using sorted per-node lists.

    events is a list of (source, target, timestamp) negative events and deltas is
    a list of window lengths in days. For every first event we use bisect to find
    the second events inside (t1, t1 + delta], so we never compare all pairs.
    Returns {delta: {pattern: {"pairs": n, "distinct_followups": m}}}.
    """
    events = sorted(events, key=lambda event: event[2])
    times = [event[2] for event in events]
    # Per-subreddit lists of event positions. Appending in sorted order keeps each
    # list sorted by time, and the parallel time lists are what bisect searches.
    outgoing = defaultdict(list)
    incoming = defaultdict(list)
    for position, (source, target, _) in enumerate(events):
        outgoing[source].append(position)
        incoming[target].append(position)
    outgoing_times = {name: [times[i] for i in found] for name, found in outgoing.items()}
    incoming_times = {name: [times[i] for i in found] for name, found in incoming.items()}

    results = {}
    for delta in deltas:
        window = timedelta(days=delta)
        table = empty_result()
        followups = {name: set() for name in PATTERNS}

        def add(pattern, second):
            table[pattern]["pairs"] += 1
            followups[pattern].add(second)

        for u, v, t1 in events:
            end = t1 + window
            # Outgoing events of u inside the window: repeated or outward.
            for second in window_slice(outgoing[u], outgoing_times[u], t1, end):
                add("repeated" if events[second][1] == v else "outward", second)
            # Outgoing events of v inside the window: reciprocal or chain.
            if v in outgoing:
                for second in window_slice(outgoing[v], outgoing_times[v], t1, end):
                    add("reciprocal" if events[second][1] == u else "chain", second)
            # Incoming events of v from a third subreddit: converging.
            for second in window_slice(incoming[v], incoming_times[v], t1, end):
                if events[second][0] != u:
                    add("converging", second)
        for name in PATTERNS:
            table[name]["distinct_followups"] = len(followups[name])
        results[delta] = table
    return results


def window_slice(positions, position_times, start, end):
    """Return the positions whose time is strictly after start and at most end."""
    low = bisect_right(position_times, start)
    high = bisect_right(position_times, end)
    return positions[low:high]


def brute_force_counts(events, deltas):
    """Reference counter that checks every pair of events. Used only in tests."""
    results = {}
    for delta in deltas:
        window = timedelta(days=delta)
        table = empty_result()
        followups = {name: set() for name in PATTERNS}
        for first_index, first in enumerate(events):
            for second_index, second in enumerate(events):
                if not first[2] < second[2] <= first[2] + window:
                    continue
                pattern = classify_pair(first, second)
                if pattern is not None:
                    table[pattern]["pairs"] += 1
                    followups[pattern].add(second_index)
        for name in PATTERNS:
            table[name]["distinct_followups"] = len(followups[name])
        results[delta] = table
    return results


def write_csv(results, path):
    """Write one row per (delta, pattern) with both counts."""
    with Path(path).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["delta_days", "pattern", "pairs", "distinct_followups"])
        for delta, table in results.items():
            for name in PATTERNS:
                writer.writerow([delta, name, table[name]["pairs"],
                                 table[name]["distinct_followups"]])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="raw SNAP .tsv/.tsv.gz file or data/processed/edges.csv")
    parser.add_argument("--deltas", type=int, nargs="+", default=[1, 3, 7],
                        help="window lengths in days (default: 1 3 7)")
    parser.add_argument("--csv", type=Path, help="optional CSV output path")
    args = parser.parse_args()
    if any(delta <= 0 for delta in args.deltas):
        parser.error("deltas must be positive")
    start = time.perf_counter()
    try:
        events = load_negative_events(args.input)
        results = count_patterns(events, args.deltas)
        if args.csv:
            write_csv(results, args.csv)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"error: {exc}\n")
    print(json.dumps({
        "negative_events": len(events),
        "counts": {str(delta): table for delta, table in results.items()},
        "runtime_seconds": round(time.perf_counter() - start, 3),
    }, indent=2))


if __name__ == "__main__":
    main()
