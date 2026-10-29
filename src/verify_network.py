"""Independently audit the exported CSVs and their sign/month partitions."""

import argparse
import csv
import json
from collections import Counter
from pathlib import Path


def read_csv(path):
    with Path(path).open(encoding="utf-8", newline="") as stream:
        yield from csv.DictReader(stream)


def verify(directory):
    directory = Path(directory)
    manifest = json.loads((directory/"manifest.json").read_text(encoding="utf-8"))
    nodes, pairs, negative_pairs, seen = set(), set(), set(), set()
    months = Counter()
    last = None
    edge_rows = {}
    negative = 0
    for row in read_csv(directory/"edges.csv"):
        key = (row["source"],row["target"],row["post_id"],row["timestamp"])
        assert key not in seen, f"duplicate event: {key}"
        seen.add(key)
        assert row["source"] != row["target"], "self-link"
        assert row["sentiment"] in ("-1","1"), "invalid sign"
        assert row["provenance"] in ("title","body","title|body"), "invalid provenance"
        order = (row["timestamp"],row["source"],row["target"],row["post_id"])
        assert last is None or last <= order, "events not sorted"
        last = order
        nodes.update((row["source"],row["target"]))
        pairs.add((row["source"],row["target"]))
        negative += row["sentiment"] == "-1"
        if row["sentiment"] == "-1":
            negative_pairs.add((row["source"],row["target"]))
        months[row["timestamp"][:7]] += 1
        edge_rows[row["event_id"]] = tuple(row.values())
    summary = manifest["summary"]
    assert len(seen) == summary["events"]
    assert len(nodes) == summary["nodes"]
    assert len(pairs) == summary["distinct_directed_pairs"]
    assert len(negative_pairs) == summary["distinct_negative_pairs"]
    assert negative == summary["negative_events"]
    partition_ids = set()
    snapshot_files = list((directory/"snapshots").glob("*.csv"))
    for path in snapshot_files:
        month,layer = path.stem.split("_",1)
        for row in read_csv(path):
            event_id = row["event_id"]
            assert event_id not in partition_ids, "overlapping snapshot partitions"
            assert edge_rows.get(event_id) == tuple(row.values()), "snapshot row differs"
            assert row["timestamp"].startswith(month), "wrong calendar month"
            assert (row["sentiment"] == "-1") == (layer == "negative"), "wrong sign layer"
            partition_ids.add(event_id)
    assert partition_ids == set(edge_rows), "snapshot partitions do not cover merged data"
    assert len(snapshot_files) == 2*manifest["calendar_months"]
    assert sum(int(r["events"]) for r in read_csv(directory/"pair_counts.csv")) == len(seen)
    for row in read_csv(directory/"monthly_statistics.csv"):
        assert int(row["events"]) == months[row["month"]]
    return {"events_verified":len(seen),"negative_events_verified":negative,
            "nodes_verified":len(nodes),"snapshot_files_verified":len(snapshot_files),
            "status":"passed"}


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory",type=Path)
    args=parser.parse_args()
    print(json.dumps(verify(args.directory),indent=2))
