"""Build reproducible signed, temporal Reddit event tables (standard library only)."""

import argparse
import csv
import gzip
import hashlib
import json
import sqlite3
import tempfile
from collections import Counter
from contextlib import closing
from datetime import datetime
from pathlib import Path

FIELDS = ["event_id", "source", "target", "post_id", "timestamp", "sentiment", "provenance"]
REQUIRED = {"SOURCE_SUBREDDIT", "TARGET_SUBREDDIT", "POST_ID", "TIMESTAMP"}
POLICY = {
    "event_identity": ["source", "target", "post_id", "timestamp"],
    "duplicates": "Equal event identity and label collapse within/across files; provenance is unioned.",
    "conflicting_labels": "Fail: do not arbitrarily choose a sign for the same event identity.",
    "parallel_edges": "Retained when post_id or timestamp differs, even for the same ordered pair.",
    "unused_attributes": "Text-property vectors are omitted; duplicate identity refers to analytical event records, not byte-identical raw rows.",
    "timestamps": "Source timestamps retained without assuming a timezone; calendar months use [start, next_start).",
    "nodes": "Union of endpoints of retained events; monthly node sets contain active endpoints only.",
    "layers": "sentiment=-1 is negative; sentiment=+1 is non-negative, not necessarily positive.",
}


def file_hashes(path):
    sha, md5 = hashlib.sha256(), hashlib.md5()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(block)
            md5.update(block)
    return {"sha256": sha.hexdigest(), "md5": md5.hexdigest(), "bytes": Path(path).stat().st_size}


def read_events(path):
    """Reject malformed rows with line context instead of silently dropping data."""
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        missing = REQUIRED - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path}: missing columns: {', '.join(sorted(missing))}")
        label = next((c for c in ("LINK_SENTIMENT", "POST_LABEL") if c in reader.fieldnames), None)
        if label is None:
            raise ValueError(f"{path}: missing LINK_SENTIMENT or POST_LABEL")
        for line, row in enumerate(reader, 2):
            try:
                if None in row or any(v is None for v in row.values()):
                    raise ValueError("wrong number of columns")
                source, target, post = (row[k].strip() for k in ("SOURCE_SUBREDDIT", "TARGET_SUBREDDIT", "POST_ID"))
                if not source or not target or not post:
                    raise ValueError("empty source, target or post_id")
                stamp = datetime.strptime(row["TIMESTAMP"], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d %H:%M:%S")
                sign = int(row[label])
                if sign not in (-1, 1):
                    raise ValueError("sentiment must be -1 or +1")
                if "LINK_SENTIMENT" in row and "POST_LABEL" in row and int(row["POST_LABEL"]) != sign:
                    raise ValueError("LINK_SENTIMENT and POST_LABEL disagree")
            except (ValueError, TypeError, AttributeError) as exc:
                raise ValueError(f"{path}: row {line}: {exc}") from exc
            yield source, target, post, stamp, sign


def summarize_sql(db, where="1"):
    rows, negative, pairs, first, last = db.execute(f"""
        SELECT COUNT(*), COALESCE(SUM(sentiment=-1),0),
        (SELECT COUNT(*) FROM (SELECT source,target FROM events WHERE {where} GROUP BY source,target)),
        MIN(timestamp),MAX(timestamp) FROM events WHERE {where}""").fetchone()
    nodes = db.execute(f"SELECT COUNT(*) FROM (SELECT source FROM events WHERE {where} UNION SELECT target FROM events WHERE {where})").fetchone()[0]
    neg_nodes = db.execute(f"SELECT COUNT(*) FROM (SELECT source FROM events WHERE {where} AND sentiment=-1 UNION SELECT target FROM events WHERE {where} AND sentiment=-1)").fetchone()[0]
    neg_pairs = db.execute(f"SELECT COUNT(*) FROM (SELECT source,target FROM events WHERE {where} AND sentiment=-1 GROUP BY source,target)").fetchone()[0]
    return {"events": rows, "negative_events": negative, "nonnegative_events": rows-negative,
            "negative_fraction": negative/rows if rows else 0.0, "nodes": nodes,
            "negative_nodes": neg_nodes, "distinct_directed_pairs": pairs,
            "distinct_negative_pairs": neg_pairs, "first_timestamp": first, "last_timestamp": last,
            "mean_total_event_degree": 2*rows/nodes if nodes else 0.0,
            "directed_pair_density": pairs/(nodes*(nodes-1)) if nodes > 1 else 0.0}


def csv_writer(path, fields):
    stream = path.open("w", encoding="utf-8", newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(fields)
    return stream, writer


def months_between(first, last):
    if first is None:
        return
    year, month = map(int, first[:7].split("-"))
    while f"{year:04d}-{month:02d}" <= last[:7]:
        yield f"{year:04d}-{month:02d}"
        year, month = (year+1, 1) if month == 12 else (year, month+1)


def prepare(inputs, output):
    """inputs maps title/body to raw TSV paths. Output must not already exist."""
    if not inputs or set(inputs) - {"title", "body"}:
        raise ValueError("provide title and/or body inputs")
    output = Path(output)
    if output.exists():
        raise FileExistsError(f"Output already exists: {output}; use a new path")
    output.parent.mkdir(parents=True, exist_ok=True)
    raw = {}
    # Stage everything next to the destination; failed validation leaves no final output.
    with tempfile.TemporaryDirectory(prefix=".network-", dir=output.parent) as temporary:
        stage = Path(temporary) / "result"
        stage.mkdir()
        with closing(sqlite3.connect(Path(temporary) / "events.sqlite")) as db:
            # Disposable staging database: do not pay for crash recovery of scratch
            # state. Final artifacts are published only after every check succeeds.
            db.execute("PRAGMA journal_mode=OFF")
            db.execute("PRAGMA synchronous=OFF")
            db.execute("PRAGMA cache_size=-131072")
            db.execute("PRAGMA temp_store=MEMORY")
            db.execute("CREATE TABLE events(source TEXT,target TEXT,post_id TEXT,timestamp TEXT,sentiment INTEGER,mask INTEGER,PRIMARY KEY(source,target,post_id,timestamp)) WITHOUT ROWID")
            for name, path in inputs.items():
                mask = 1 if name == "title" else 2
                stats = Counter()
                for event in read_events(path):
                    stats["rows"] += 1
                    stats["negative_rows"] += event[-1] == -1
                    if event[0] == event[1]:
                        stats["self_link_rows_removed"] += 1
                        continue
                    old = db.execute("SELECT sentiment,mask FROM events WHERE source=? AND target=? AND post_id=? AND timestamp=?", event[:4]).fetchone()
                    if old:
                        if old[0] != event[-1]:
                            raise ValueError(f"Conflicting labels for event {event[:4]}")
                        stats["duplicate_observations"] += 1
                        stats["within_source_duplicates"] += bool(old[1] & mask)
                        stats["cross_source_overlap"] += not bool(old[1] & mask)
                        db.execute("UPDATE events SET mask=mask|? WHERE source=? AND target=? AND post_id=? AND timestamp=?", (mask, *event[:4]))
                    else:
                        db.execute("INSERT INTO events VALUES(?,?,?,?,?,?)", (*event, mask))
                raw[name] = {key: stats[key] for key in ("rows", "negative_rows", "self_link_rows_removed", "duplicate_observations", "within_source_duplicates", "cross_source_overlap")}
                raw[name].update({"filename": Path(path).name, **file_hashes(path)})
                db.commit()
            db.execute("CREATE INDEX time_index ON events(timestamp,source,target,post_id)")
            summary = summarize_sql(db)
            source_summaries = {name: summarize_sql(db, f"(mask & {1 if name == 'title' else 2}) != 0") for name in inputs}
            overlap = db.execute("SELECT COUNT(*) FROM events WHERE mask=3").fetchone()[0]
            monthly = []
            (stage / "snapshots").mkdir()
            # Write globally ordered events once; every row belongs to exactly one sign layer.
            merged_stream, merged_writer = csv_writer(stage/"edges.csv", FIELDS)
            sample_stream, sample_writer = csv_writer(stage/"sample_10000.csv", FIELDS)
            layer_streams = []
            current_month = None
            event_id = 0
            try:
                for source, target, post, stamp, sign, mask in db.execute("SELECT * FROM events ORDER BY timestamp,source,target,post_id"):
                    month = stamp[:7]
                    if month != current_month:
                        for stream in layer_streams:
                            stream.close()
                        layer_streams = []
                        writers = {}
                        for layer in ("negative", "nonnegative"):
                            stream, writer = csv_writer(stage/"snapshots"/f"{month}_{layer}.csv", FIELDS)
                            layer_streams.append(stream)
                            writers[layer] = writer
                        current_month = month
                    event_id += 1
                    row = [event_id, source, target, post, stamp, sign, {1:"title", 2:"body", 3:"title|body"}[mask]]
                    merged_writer.writerow(row)
                    writers["negative" if sign == -1 else "nonnegative"].writerow(row)
                    if event_id <= 10000:
                        sample_writer.writerow(row)
            finally:
                merged_stream.close()
                sample_stream.close()
                for stream in layer_streams:
                    stream.close()
            for month in months_between(summary["first_timestamp"], summary["last_timestamp"]):
                year, number = map(int, month.split("-"))
                next_month = f"{year+1:04d}-01" if number == 12 else f"{year:04d}-{number+1:02d}"
                row = {"month": month, **summarize_sql(db, f"timestamp>='{month}-01 00:00:00' AND timestamp<'{next_month}-01 00:00:00'")}
                monthly.append(row)
                for layer in ("negative", "nonnegative"):
                    path = stage/"snapshots"/f"{month}_{layer}.csv"
                    if not path.exists():
                        stream, _ = csv_writer(path, FIELDS)
                        stream.close()
            fields = ["month", *summary]
            stream, writer = csv_writer(stage/"monthly_statistics.csv", fields)
            with stream:
                writer.writerows([[row[k] for k in fields] for row in monthly])
            stream, writer = csv_writer(stage/"pair_counts.csv", ["source", "target", "events", "negative_events", "nonnegative_events"])
            with stream:
                writer.writerows(db.execute("SELECT source,target,COUNT(*),SUM(sentiment=-1),SUM(sentiment=1) FROM events GROUP BY source,target ORDER BY source,target"))
            stream, writer = csv_writer(stage/"dataset_statistics.csv", ["measure", "merged", *inputs])
            with stream:
                writer.writerows([[key, summary[key], *[source_summaries[name][key] for name in inputs]] for key in summary])
            retained = summary["events"]
            assert retained == sum(x["rows"]-x["self_link_rows_removed"]-x["duplicate_observations"] for x in raw.values())
            assert retained == sum(x["events"] for x in monthly)
            manifest = {"schema_version": 1, "complete_title_and_body": set(inputs)=={"title","body"},
                        "policy": POLICY, "inputs": raw, "summary": summary,
                        "by_source": source_summaries, "overlap_events": overlap,
                        "calendar_months": len(monthly),
                        "sample_note": "First 10,000 retained events in time order; development fixture, not a representative sample.",
                        "output_hashes": {str(p.relative_to(stage)).replace('\\','/'):file_hashes(p) for p in sorted(stage.rglob("*.csv"))}}
            (stage/"manifest.json").write_text(json.dumps(manifest, indent=2)+"\n", encoding="utf-8")
        stage.rename(output)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--title", type=Path)
    parser.add_argument("--body", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        manifest = prepare({k:v for k,v in (("title",args.title),("body",args.body)) if v}, args.output)
    except (OSError, ValueError, sqlite3.Error) as exc:
        parser.exit(2, f"error: {exc}\n")
    print(json.dumps(manifest["summary"], indent=2))


if __name__ == "__main__":
    main()
