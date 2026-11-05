# Conflict Cascades in Reddit Communities

Investigating recurring patterns of negative interactions between Reddit communities using the SNAP Reddit Hyperlink Network.

## Setup

Requires Python 3.10 or newer. Role A (`prepare_network.py`, `verify_network.py`),
`reddit_summary.py` and `pattern_counts.py` use the standard library only. The RQ1
and RQ3 scripts and the figures need three packages:

```powershell
python -m pip install --user pandas numpy matplotlib
python src/reddit_summary.py data/example.tsv
python -m unittest discover -s tests -v
```

`python -m unittest discover -s tests -v` runs every test (44), including the RQ1,
RQ2 and RQ3 tests. `python -m pytest tests` also works.

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

## Status (progress report, November 2026)

| Part | Script | Status |
|---|---|---|
| A: cleaned network, monthly layers | `prepare_network.py`, `verify_network.py` | done |
| B: RQ1 concentration, reciprocity, degree distribution | `concentration.py` | done |
| C: RQ2 pattern counts on the real network | `pattern_counts.py`, `make_pattern_outputs.py` | done |
| C: RQ2 null models (time and sign shuffles) | | planned for the final report |
| D: RQ3 cut-offs, candidates, labels, split | `prediction_setup.py` | done |
| D: RQ3 features, baselines, logistic regression | | planned for the final report |

## Reproduce all results and figures

From the repository root, after the setup above:

```powershell
# RQ1 (Role B): Table 3 numbers and Figure 1a-c
python src/concentration.py data/processed/edges.csv --outdir figures

# RQ2 (Role C): Table 4 counts and Figure 2 (distinct follow-ups, as in the report)
python src/pattern_counts.py data/processed/edges.csv --csv data/processed/patterns.csv
python src/make_pattern_outputs.py data/processed/patterns.csv --outdir figures --metric distinct_followups

# RQ3 (Role D): Table 5 candidate and label statistics
python src/prediction_setup.py data/processed/edges.csv --out data/processed/rq3_summary.csv
```

Outputs:

- `figures/fig_degree_dist.pdf`, `fig_concentration.pdf`, `fig_monthly.pdf`: Figure 1a-c.
- `figures/rq1_summary.json`, `rq1_concentration.csv`, `rq1_table.tex`: R_k, reciprocity,
  power-law fits; `rq1_degrees.csv` and `rq1_monthly.csv`: per-node and per-month tables.
- `figures/pattern_counts.pdf` and `pattern_table_*.tex`: Figure 2 and Table 4.
- `data/processed/patterns.csv`: pairs and distinct follow-ups per pattern and window.
- `data/processed/rq3_summary.csv`: weeks, candidates, positives, positive rate and
  coverage per split.

## Role A: cleaned network and monthly layers

The new pipeline is separate from `reddit_summary.py`, whose raw-data behavior is
unchanged. Both use the Python standard library only.

```powershell
python src/verify_network.py data/processed
python src/prepare_network.py --title data/soc-redditHyperlinks-title.tsv.gz --body data/soc-redditHyperlinks-body.tsv --output data/processed_rerun
python -m unittest discover -s tests -v
```

The verified cleaned dataset is included in `data/processed/`, ready for the
concentration, temporal-pattern and prediction scripts. It contains the complete
858,488-event table, 82 monthly sign layers, pair counts, statistics, a 10,000-event
development sample and the checksum manifest. Dataset bytes are preserved by
`.gitattributes`, so checksum verification is independent of checkout platform.

The preparation command above regenerates the dataset into a separate directory;
its output directory must not already exist. Inputs can also be `.tsv.gz`.
Raw extracted TSVs and additional `data/processed*` reruns remain ignored by Git.

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

## Role B: RQ1 concentration (`src/concentration.py`)

Total degree counts parallel events (in + out). Nodes are ranked by total degree with
ties broken by name, and the top `ceil(kN/100)` nodes form the top k% for k = 1, 5, 10.
`R_k` is the share of negative events touching the top k% divided by the share of all
events touching it; because activity is concentrated too, `R_k` cannot exceed
`1 / (share of all events)`. Reciprocity is the fraction of negative events u->v
for which a negative v->u exists anywhere in the data. The power-law exponent uses
the discrete maximum-likelihood approximation with `k_min` chosen by
Kolmogorov-Smirnov distance. The monthly figure omits months with fewer than 1,000
events (the partial December 2013).

Results: R_1 = 1.16, R_5 = 1.04, R_10 = 1.02 (top 1% = 672 communities touching
78.3% of all and 90.9% of negative events); 11.6% of negative events and 6.7% of
distinct negative pairs are reciprocated.

## Role C: RQ2 pattern counts (`src/pattern_counts.py`)

Reads a raw SNAP `.tsv`/`.tsv.gz` file or `data/processed/edges.csv` (same results;
tested). For each negative event, binary search over per-community time-ordered lists
finds follow-ups in `(t1, t1 + delta]`; events with equal timestamps are never
follow-ups of each other. Both pair counts and distinct follow-up events are reported;
the report uses distinct follow-ups for Figure 2 because bursts inflate pair counts.
Counting all three windows over the 82,210 negative events takes under 20 seconds.

## Role D: RQ3 prediction setup (`src/prediction_setup.py`)

- Weekly cut-offs `T` start 90 days after the first event and advance by 7 days while
  the label window `[T, T+7d)` fits in the data.
- Candidates at `T`: ordered pairs `(u, v)` with an event between `u` and `v`, in either
  direction, in `[T-90d, T)`.
- Label: 1 if a negative event `u -> v` occurs in `[T, T+7d)`.
- Split by cut-off: train 2014-2015, validation 2016, test January-April 2017. A week
  whose label window crosses a split boundary is dropped, so labels never leak.
- Coverage is the share of distinct negative pairs in the label window that were
  candidates: the highest recall any model on this candidate set can reach.

| Split | Weeks | Candidates | Positives | Positive rate | Coverage |
|---|---:|---:|---:|---:|---:|
| Train (2014-15) | 91 | 6,013,642 | 21,885 | 0.36% | 57.5% |
| Val (2016) | 51 | 4,309,944 | 14,956 | 0.35% | 56.9% |
| Test (Jan-Apr 2017) | 16 | 1,493,324 | 5,126 | 0.34% | 55.6% |

## Acknowledgment

Generative AI assisted with the initial code, tests, and documentation.
Team member(s) reviewed and approved the AI-generated code. The project team
remains responsible for the correctness of submitted code, analyses, and conclusions.
