import argparse
import csv
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))

LABELS = {"linkup": "Linkup", "parallel": "Parallel", "exa": "Exa", "perplexity": "Perplexity"}

WINNER_BAND = ["#93c5fd", "#3b82f6", "#1d4ed8"]
OTHER_BAND = ["#dbdee3", "#b8bdc6", "#94a0ae"]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default=os.path.join(HERE, "..", "results", "scorecard.csv"))
    ap.add_argument("--out", default=os.path.join(HERE, "..", "results", "scorecard.png"))
    args = ap.parse_args()

    with open(args.inp, newline="") as f:
        rows = list(csv.DictReader(f))
    rows.sort(key=lambda r: int(r["within_25"]), reverse=True)

    bands = [("within_10", "within 10%"), ("within_25", "within 25%"), ("within_50", "within 50%")]
    n_api = len(rows)
    n = rows[0]["n"]
    winner = rows[0]["api"]

    fig, ax = plt.subplots(figsize=(9.4, 5.4))
    group_w = 0.82
    bar_w = group_w / len(bands)
    x = list(range(n_api))

    for bi, (key, _) in enumerate(bands):
        offset = (bi - (len(bands) - 1) / 2) * bar_w
        for xi, r in zip(x, rows):
            is_win = r["api"] == winner
            ax.bar(xi + offset, int(r[key]), width=bar_w * 0.92,
                   color=(WINNER_BAND if is_win else OTHER_BAND)[bi],
                   edgecolor="white", linewidth=0.6, zorder=3)

    ax.set_xticks(x)
    ax.set_xticklabels([LABELS.get(r["api"], r["api"]) for r in rows], fontsize=11)
    for tick, r in zip(ax.get_xticklabels(), rows):
        if r["api"] == winner:
            tick.set_color("#1d4ed8")
            tick.set_fontweight("bold")

    ax.set_ylabel("Share of companies within error band (%)", fontsize=11)
    ax.set_ylim(0, 100)
    ax.set_yticks(range(0, 101, 20))
    ax.set_title("Funding-retrieval accuracy: Linkup vs. the field\n"
                 f"total funding raised vs. Crunchbase golden value (n={n} companies)",
                 fontsize=13, fontweight="bold", pad=14)
    ax.grid(axis="y", color="#eef1f5", zorder=0)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)

    from matplotlib.patches import Patch
    handles = [Patch(facecolor=WINNER_BAND[bi], label=lbl) for bi, (_, lbl) in enumerate(bands)]
    handles.append(Patch(facecolor=OTHER_BAND[1], label="other APIs"))
    ax.legend(handles=handles, title="accuracy band", loc="upper right",
              frameon=False, fontsize=9)

    fig.tight_layout()
    fig.savefig(args.out, dpi=150)
    print(f"Wrote {args.out}")

if __name__ == "__main__":
    main()
