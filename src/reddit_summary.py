"""Initial descriptive analysis of directed negative Reddit hyperlinks."""

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path

REQUIRED_COLUMNS = {"SOURCE_SUBREDDIT", "TARGET_SUBREDDIT", "TIMESTAMP"}


def summarize(path):
    """Stream a TSV and summarize negative events and unique directed edges.

    Repeated links count as separate events. Self-links are retained. A negative
    label is a dataset annotation, not evidence of a causal conflict cascade.
    """
    total = negative = 0
    nodes = set()
    edges = set()
    first = last = None
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Missing columns: {', '.join(sorted(missing))}")
        label_column = next((name for name in ("LINK_SENTIMENT", "POST_LABEL")
                             if name in reader.fieldnames), None)
        if label_column is None:
            raise ValueError("Missing label column: LINK_SENTIMENT or POST_LABEL")
        for line, row in enumerate(reader, start=2):
            try:
                source = row["SOURCE_SUBREDDIT"].strip()
                target = row["TARGET_SUBREDDIT"].strip()
                if not source or not target:
                    raise ValueError("subreddit names must be nonempty")
                sentiment = int(row[label_column])
                if sentiment not in {-1, 1}:
                    raise ValueError("label must be -1 or 1")
                timestamp = datetime.strptime(row["TIMESTAMP"], "%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError, AttributeError) as exc:
                raise ValueError(f"Invalid TSV row {line}: {exc}") from exc
            total += 1
            if sentiment == -1:
                negative += 1
                nodes.update((source, target))
                edges.add((source, target))
                first = timestamp if first is None else min(first, timestamp)
                last = timestamp if last is None else max(last, timestamp)
    return {
        "total_events": total,
        "negative_events": negative,
        "negative_event_fraction": negative / total if total else 0.0,
        "negative_nodes": len(nodes),
        "unique_directed_negative_edges": len(edges),
        "negative_self_edges": sum(source == target for source, target in edges),
        "first_negative_timestamp": str(first) if first else None,
        "last_negative_timestamp": str(last) if last else None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Reddit hyperlink TSV file")
    args = parser.parse_args()
    try:
        result = summarize(args.input)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"error: {exc}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
