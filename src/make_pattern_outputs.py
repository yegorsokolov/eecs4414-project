"""Turn the pattern-count CSV into LaTeX tables and a figure for the report."""

import argparse
import csv
import math
import sys
from pathlib import Path

PATTERNS = ("reciprocal", "repeated", "outward", "converging", "chain")
DELTAS = (1, 3, 7)
METRICS = ("distinct_followups", "pairs")
REQUIRED_COLUMNS = {"delta_days", "pattern", "pairs", "distinct_followups"}
AXIS_LABELS = {"distinct_followups": "Distinct follow-up events (log scale)",
               "pairs": "Pairs (log scale)"}
# Okabe-Ito colour-blind-safe palette, with a different marker and line style
# per pattern so colour is never the only difference.
COLORS = ("#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00")
MARKERS = ("o", "s", "^", "D", "v")
LINE_STYLES = ("-", "--", "-.", ":", (0, (5, 1, 1, 1, 1, 1)))


def read_counts(path):
    """Read the CSV into {(delta_days, pattern): {"pairs": n, "distinct_followups": m}}.

    Raises ValueError for missing columns, bad numbers, or a missing
    (delta, pattern) combination, so a bad CSV fails loudly.
    """
    counts = {}
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Missing columns: {', '.join(sorted(missing))}")
        for line, row in enumerate(reader, start=2):
            try:
                key = (int(row["delta_days"]), row["pattern"].strip())
                counts[key] = {"pairs": int(row["pairs"]),
                               "distinct_followups": int(row["distinct_followups"])}
            except (ValueError, TypeError, AttributeError) as exc:
                raise ValueError(f"Invalid CSV row {line}: {exc}") from exc
    for delta in DELTAS:
        for pattern in PATTERNS:
            if (delta, pattern) not in counts:
                raise ValueError(f"CSV has no row for delta {delta}, pattern {pattern}")
    return counts


def format_count(number):
    """Write a count with LaTeX thousands separators, for example 26{,}578."""
    return f"{number:,}".replace(",", "{,}")


def column_heading(delta):
    """Return the table column heading for a window length, such as '3 days'."""
    return f"{delta} day" if delta == 1 else f"{delta} days"


def write_table(counts, metric, path):
    """Write a bare booktabs tabular (no float, caption or label) for one metric."""
    lines = ["\\begin{tabular}{lrrr}",
             "\\toprule",
             " & ".join(["Pattern"] + [column_heading(d) for d in DELTAS]) + " \\\\",
             "\\midrule"]
    for pattern in PATTERNS:
        cells = [pattern.capitalize()]
        cells += [format_count(counts[(delta, pattern)][metric]) for delta in DELTAS]
        lines.append(" & ".join(cells) + " \\\\")
    lines += ["\\bottomrule", "\\end{tabular}"]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_figure(counts, metric, path):
    """Save a one-column line chart of the metric against window length as a PDF.

    matplotlib is imported here so the tables can still be written without it.
    The y axis is logarithmic and extends one decade above the data so the
    legend sits in empty space above the lines.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter, NullFormatter

    matplotlib.rcParams.update({"font.size": 7, "pdf.fonttype": 42})
    figure, axes = plt.subplots(figsize=(3.3, 2.4), layout="constrained")
    for index, pattern in enumerate(PATTERNS):
        values = [counts[(delta, pattern)][metric] for delta in DELTAS]
        axes.plot(DELTAS, values, label=pattern.capitalize(), color=COLORS[index],
                  marker=MARKERS[index], linestyle=LINE_STYLES[index],
                  linewidth=1, markersize=3.5)
    axes.set_yscale("log")
    lowest = min(c[metric] for c in counts.values())
    highest = max(c[metric] for c in counts.values())
    axes.set_ylim(10 ** math.floor(math.log10(lowest)) / 2,
                  10 ** (math.ceil(math.log10(highest)) + 1))
    axes.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{int(value):,}"))
    axes.yaxis.set_minor_formatter(NullFormatter())
    axes.set_xticks(DELTAS)
    axes.set_xlim(DELTAS[0] - 0.4, DELTAS[-1] + 0.4)
    axes.set_xlabel("Window length (days)")
    axes.set_ylabel(AXIS_LABELS[metric])
    axes.legend(loc="upper center", ncol=3, frameon=False, handlelength=2.5,
                columnspacing=1.0, handletextpad=0.4)
    figure.savefig(path, format="pdf")
    plt.close(figure)


def make_outputs(csv_path, outdir, metric):
    """Write both tables and the figure into outdir and return the written paths.

    The tables are always written. If matplotlib is missing, a message is printed
    and the figure is left out of the returned list.
    """
    counts = read_counts(csv_path)
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    written = []
    for metric_name, suffix in (("distinct_followups", "distinct"), ("pairs", "pairs")):
        table_path = outdir / f"pattern_table_{suffix}.tex"
        write_table(counts, metric_name, table_path)
        written.append(table_path)
    figure_path = outdir / "pattern_counts.pdf"
    try:
        write_figure(counts, metric, figure_path)
        written.append(figure_path)
    except ImportError:
        print("matplotlib is not installed, so the figure was skipped. "
              "Install it with: python -m pip install matplotlib", file=sys.stderr)
    return written


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path, help="CSV written by pattern_counts.py --csv")
    parser.add_argument("--outdir", type=Path, default=Path("figures"),
                        help="folder for the .tex tables and PDF figure (default: figures)")
    parser.add_argument("--metric", choices=METRICS, default="distinct_followups",
                        help="count plotted in the figure (default: distinct_followups)")
    args = parser.parse_args()
    try:
        written = make_outputs(args.csv, args.outdir, args.metric)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"error: {exc}\n")
    for path in written:
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
