# Conflict Cascades in Reddit Communities

EECS 4414 group project investigating recurring patterns of negative interactions
between Reddit communities using the SNAP Reddit Hyperlink Network.

## Setup

Requires Python 3.10 or newer. No external packages are needed.

```powershell
python src/reddit_summary.py data/example.tsv
python -m unittest discover -s tests -v
```

`data/example.tsv` is a synthetic test fixture with four events, three negative
labels, and two distinct directed negative edges.

## Dataset

The [SNAP Reddit Hyperlink Network](https://snap.stanford.edu/data/soc-RedditHyperlinks.html)
contains directed, timestamped links between subreddits. The title hyperlink file
is included as `data/soc-redditHyperlinks-title.tsv.gz`. The body file was downloaded
locally on October 29, 2026 and verified against SNAP's published MD5.
Download details and checksums are in [data/DOWNLOAD_INFO.md](data/DOWNLOAD_INFO.md).

Extract the archive and run the summary:

```powershell
python -c "import gzip, shutil; shutil.copyfileobj(gzip.open('data/soc-redditHyperlinks-title.tsv.gz', 'rb'), open('data/soc-redditHyperlinks-title.tsv', 'wb'))"
python src/reddit_summary.py data/soc-redditHyperlinks-title.tsv
```

The archive is tracked in Git; extracted TSVs are ignored.

## Current analysis

The summary command reports event counts, the fraction of negative events,
communities participating in negative links, distinct directed negative edges,
self-edges, and the time range of negative events.

Input is tab-separated with `SOURCE_SUBREDDIT`, `TARGET_SUBREDDIT`, `TIMESTAMP`,
and `LINK_SENTIMENT` (or `POST_LABEL`). If both label columns exist,
`LINK_SENTIMENT` takes precedence. Labels are -1 for negative and 1 for neutral
or positive. Timestamps use `YYYY-MM-DD HH:MM:SS`; no timezone is assigned.

Repeated events and self-links are retained. Distinct edges are counted by
ordered source-target pairs. The reader streams input and keeps distinct nodes
and edges in memory. Malformed rows produce an error with the input line number.

## Planned analysis

- Concentration of negative links by community degree.
- Temporal interaction patterns and randomized baselines.
- Prediction of subsequent negative links using activity and sequence features.

## Role A: cleaned network and monthly layers

The new pipeline is separate from `reddit_summary.py`, whose raw-data behavior is
unchanged. Both use the Python standard library only.

```powershell
python src/prepare_network.py --title data/soc-redditHyperlinks-title.tsv --body data/soc-redditHyperlinks-body.tsv --output data/processed
python src/verify_network.py data/processed
python -m unittest discover -s tests -v
```

The output directory must not already exist. Use a new directory for a rerun.
Inputs can also be `.tsv.gz`. Large raw and generated CSV files are ignored by Git.

- `edges.csv`: time-ordered directed events, retaining `post_id`, sign and provenance.
- `snapshots/YYYY-MM_negative.csv` and `..._nonnegative.csv`: disjoint monthly sign layers.
- `pair_counts.csv`: directed pair event counts, with the two signs separate.
- `monthly_statistics.csv` and `dataset_statistics.csv`: measured summary tables.
- `sample_10000.csv`: earliest retained events for development, not a random sample.
- `manifest.json`: policy, raw counts, hashes and output checksums.

The identity key is `(source, target, post_id, timestamp)`. Duplicate event records
with the same sign collapse and union title/body provenance. Conflicting signs
fail validation. Properties unused by the analysis do not enter this key. Distinct
posts/timestamps preserve parallel edges. Self-links are removed. Timestamps retain
the release's unspecified timezone; sort ties must not be treated as earlier/later
events. Monthly windows are half-open. Temporal motifs must use the full event
table to include sequences spanning month boundaries.

The full run retained **858,488 events**, including **82,210 negative events
(9.58%)**, across **67,180 endpoint communities** and **339,643 directed pairs**.
There were no self-links, duplicate event keys, sign conflicts or title/body event
overlaps in these files. There are **41 calendar months and 82 sign-layer CSVs**.
December 2013 is a partial boundary month with 34 events. These are file-level
measurements, which differ from SNAP's landing-page headline totals; the mismatch
has not been resolved by altering the data.

The report folder, report content, and generated data handoff archive are local
artifacts excluded from version control.

## Acknowledgment

Generative AI assisted with the initial code, tests, and documentation.
Team member(s) reviewed and approved the AI-generated code. The project team
remains responsible for the correctness of submitted code, analyses, and conclusions.
