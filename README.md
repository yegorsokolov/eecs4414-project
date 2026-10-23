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
is included as `data/soc-redditHyperlinks-title.tsv.gz`. The body file is not included.
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

## Acknowledgment

Generative AI assisted with the initial code, tests, and documentation.
Team member(s) reviewed and approved the AI-generated code. The project team
remains responsible for the correctness of submitted code, analyses, and conclusions.
