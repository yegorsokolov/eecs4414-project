"""Role B (RQ1): is conflict concentrated in a few communities?

Input : Role A's data/processed/edges.csv (or a raw SNAP TSV / .tsv.gz).
Output: <outdir>/rq1_summary.json, rq1_concentration.csv, rq1_monthly.csv,
        rq1_degrees.csv, rq1_table.tex and three PDF figures
        (fig_degree_dist.pdf, fig_concentration.pdf, fig_monthly.pdf).

Definitions (match Section 2 of the report):
    degree k_i = in-degree + out-degree, counting parallel edges
    V_k        top k% of nodes by total degree (ties broken by name)
    R_k        (share of negative edges touching V_k) / (share of all edges touching V_k)
    reciprocity fraction of negative edges u->v for which a negative v->u ever occurs

Usage:
    python src/concentration.py data/processed/edges.csv --outdir figures
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from prediction_setup import load_edges

KS = (1, 5, 10)
COLORS = {"all": "#0072B2", "neg": "#D55E00"}


def degrees(df: pd.DataFrame) -> pd.DataFrame:
    neg = df[df["sign"] < 0]
    out = pd.DataFrame({
        "out": df.groupby("src").size(), "in": df.groupby("dst").size(),
        "neg_out": neg.groupby("src").size(), "neg_in": neg.groupby("dst").size(),
    }).fillna(0).astype(int)
    out["total"] = out["out"] + out["in"]
    out["neg_total"] = out["neg_out"] + out["neg_in"]
    out["neg_fraction"] = np.where(out["total"] > 0, out["neg_total"] / out["total"], 0.0)
    return out.sort_index()


def concentration(df: pd.DataFrame, deg: pd.DataFrame, ks=KS) -> pd.DataFrame:
    n = len(deg)
    # rank by total degree, ties broken by name so the result is reproducible
    order = deg.assign(name=deg.index).sort_values(["total", "name"], ascending=[False, True]).index
    neg = (df["sign"] < 0).to_numpy()
    rows = []
    for k in ks:
        top = set(order[: math.ceil(n * k / 100)])
        touch = df["src"].isin(top).to_numpy() | df["dst"].isin(top).to_numpy()
        share_all = touch.mean()
        share_neg = touch[neg].mean()
        rows.append({"k_percent": k, "nodes": len(top), "share_all_links": share_all,
                     "share_negative_links": share_neg, "R_k": share_neg / share_all})
    return pd.DataFrame(rows)


def reciprocity(df: pd.DataFrame) -> dict:
    neg = df[df["sign"] < 0][["src", "dst"]]
    pairs = set(zip(neg["src"], neg["dst"]))
    ev = np.fromiter(((d, s) in pairs for s, d in zip(neg["src"], neg["dst"])), bool, len(neg))
    distinct = np.fromiter(((d, s) in pairs for s, d in pairs), bool, len(pairs))
    return {"events_reciprocated": float(ev.mean()), "distinct_pairs_reciprocated": float(distinct.mean()),
            "negative_events": int(len(neg)), "distinct_negative_pairs": int(len(pairs))}


def monthly(df: pd.DataFrame) -> pd.DataFrame:
    m = df["ts"].dt.to_period("M").astype(str)
    g = pd.DataFrame({"month": m, "neg": (df["sign"] < 0).to_numpy()}).groupby("month")["neg"].agg(["size", "sum"])
    g.columns = ["total_links", "negative_links"]
    g["negative_share_pct"] = 100 * g["negative_links"] / g["total_links"]
    return g.reset_index()


def powerlaw_alpha(k: np.ndarray) -> dict:
    """Discrete power-law MLE (Clauset-Shalizi-Newman approximation), k_min chosen by KS distance."""
    k = np.sort(k[k > 0])
    best = None
    for kmin in np.unique(k)[:: max(1, len(np.unique(k)) // 60)]:
        x = k[k >= kmin]
        if len(x) < 50:
            continue
        a = 1 + len(x) / np.sum(np.log(x / (kmin - 0.5)))
        xs = np.unique(x)
        emp = np.array([(x >= v).mean() for v in xs])
        mod = (xs / kmin) ** (1 - a)  # continuous approximation of the tail CCDF
        ks = np.max(np.abs(emp - mod))
        if best is None or ks < best["ks"]:
            best = {"alpha": float(a), "kmin": int(kmin), "n_tail": int(len(x)), "ks": float(ks)}
    return best or {}


def _style():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.size": 8, "axes.spines.top": False, "axes.spines.right": False,
                         "figure.figsize": (3.3, 2.3), "axes.grid": True, "grid.alpha": .25})
    return plt


def fig_degree(deg, path, alpha):
    plt = _style()
    fig, ax = plt.subplots()
    for col, lab, c, mk in (("total", "All links", COLORS["all"], "o"), ("neg_total", "Negative links", COLORS["neg"], "s")):
        k = deg[col][deg[col] > 0]
        pk = k.value_counts().sort_index() / len(k)
        ax.loglog(pk.index, pk.values, mk, ms=2.5, color=c, label=lab, alpha=.8)
    ax.set_xlabel("Total degree $k$ (links)")
    ax.set_ylabel("$P(k)=N_k/N$")
    if alpha:
        ax.set_title(rf"all links: $\hat\alpha\approx{alpha['alpha']:.2f}$ ($k\geq{alpha['kmin']}$)", fontsize=7)
    ax.legend(frameon=False)
    fig.tight_layout(); fig.savefig(path); plt.close(fig)


def fig_conc(conc, path):
    plt = _style()
    fig, ax = plt.subplots()
    x = np.arange(len(conc)); w = .38
    ax.bar(x - w / 2, 100 * conc["share_all_links"], w, color=COLORS["all"], label="Share of all links")
    ax.bar(x + w / 2, 100 * conc["share_negative_links"], w, color=COLORS["neg"], label="Share of negative links")
    for i, r in conc.iterrows():
        ax.text(i, 100 * max(r["share_all_links"], r["share_negative_links"]) + 2, f"$R_k$={r['R_k']:.2f}", ha="center", fontsize=7)
    ax.set_xticks(x, [f"Top {k}%" for k in conc["k_percent"]])
    ax.set_ylabel("Links touching the group (%)"); ax.set_ylim(0, 155)
    ax.legend(frameon=False, loc="upper center", fontsize=7, ncol=1)
    fig.tight_layout(); fig.savefig(path); plt.close(fig)


def fig_monthly(mon, path):
    plt = _style()
    fig, ax = plt.subplots()
    mon = mon[mon["total_links"] >= 1000]  # drop partial boundary months (e.g. Dec 2013: 34 events)
    x = pd.to_datetime(mon["month"])
    ax.plot(x, mon["negative_links"], color=COLORS["all"], lw=1.2, label="Negative links (count)")
    ax.set_ylabel("Negative links per month"); ax.set_xlabel("Month")
    ax2 = ax.twinx(); ax2.spines["right"].set_visible(True)
    ax2.plot(x, mon["negative_share_pct"], color=COLORS["neg"], lw=1.2, ls="--", label="Share of links (%)")
    ax2.set_ylabel("Negative share (%)"); ax2.set_ylim(0, 16); ax2.grid(False)
    h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
    ax.set_ylim(0, mon["negative_links"].max() * 1.45)
    ax.legend(h1 + h2, l1 + l2, frameon=False, fontsize=7, loc="upper left", ncol=1)
    fig.autofmt_xdate(rotation=30); fig.tight_layout(); fig.savefig(path); plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edges")
    ap.add_argument("--outdir", type=Path, default=Path("figures"))
    a = ap.parse_args()
    a.outdir.mkdir(parents=True, exist_ok=True)
    df = load_edges(a.edges)
    deg = degrees(df)
    conc = concentration(df, deg)
    rec = reciprocity(df)
    mon = monthly(df)
    alpha = powerlaw_alpha(deg["total"].to_numpy())
    deg.to_csv(a.outdir / "rq1_degrees.csv"); conc.to_csv(a.outdir / "rq1_concentration.csv", index=False)
    mon.to_csv(a.outdir / "rq1_monthly.csv", index=False)
    summary = {"links": int(len(df)), "negative_links": int((df["sign"] < 0).sum()), "nodes": int(len(deg)),
               "reciprocity": rec, "powerlaw_all": alpha, "powerlaw_negative": powerlaw_alpha(deg["neg_total"].to_numpy())}
    (a.outdir / "rq1_summary.json").write_text(json.dumps(summary, indent=2))
    with open(a.outdir / "rq1_table.tex", "w") as f:  # rows for Table 3 of the report
        for _, r in conc.iterrows():
            f.write(f"{int(r.k_percent)}\\% & {100*r.share_all_links:.1f}\\% & {100*r.share_negative_links:.1f}\\% & {r.R_k:.2f}\\\\\n")
    fig_degree(deg, a.outdir / "fig_degree_dist.pdf", alpha)
    fig_conc(conc, a.outdir / "fig_concentration.pdf")
    fig_monthly(mon, a.outdir / "fig_monthly.pdf")
    print(conc.to_string(index=False)); print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()