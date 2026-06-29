import os
from collections import defaultdict
from statistics import mean

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from eval import load, completeness, match, filled, PROVS, FIELDS

HERE = os.path.dirname(os.path.abspath(__file__))
CHARTS = os.path.join(HERE, "charts")

LABEL = {"linkup": "Linkup", "exa": "Exa", "perplexity": "Perplexity", "parallel": "Parallel"}
LINKUP = "#1d6fe0"
GREY   = "#9aa3ad"
RIGHT  = "#34a853"
WRONG  = "#ea4335"
EMPTY  = "#cfd4da"

plt.rcParams.update({
    "font.size": 11, "axes.spines.top": False, "axes.spines.right": False,
    "axes.titleweight": "bold", "figure.dpi": 140,
})

def compute():
    gt, people = load()
    comp = defaultdict(list)
    fagg = {p: defaultdict(int) for p in PROVS}
    cnt = defaultdict(int)
    corr = {p: defaultdict(int) for p in PROVS}

    for u, pp in people.items():
        g = gt.get(u)
        for p in PROVS:
            d = pp["resp"].get(p, {})
            sc, pts = completeness(d)
            comp[p].append(sc); cnt[p] += 1
            for f in FIELDS:
                fagg[p][f] += pts[f]
            if g:
                co = d.get("current_company", "")
                corr[p]["n"] += 1
                if not filled(co):
                    corr[p]["empty"] += 1
                elif match(co, g["current_company"]):
                    corr[p]["right"] += 1
                else:
                    corr[p]["wrong"] += 1
    return comp, corr, fagg, cnt

def bar_colors(order):
    return [LINKUP if p == "linkup" else GREY for p in order]

def chart_completeness(comp):
    order = sorted(PROVS, key=lambda p: mean(comp[p]))
    vals = [mean(comp[p]) for p in order]
    fig, ax = plt.subplots(figsize=(7, 3.6))
    bars = ax.barh([LABEL[p] for p in order], vals, color=bar_colors(order))
    for b, v in zip(bars, vals):
        ax.text(v + 1, b.get_y() + b.get_height() / 2, f"{v:.1f}",
                va="center", fontweight="bold")
    ax.set_xlim(0, 105)
    ax.set_xlabel("Mean completeness score (0–100)")
    ax.set_title("Completeness — did it fill the requested fields?")
    fig.tight_layout()
    fig.savefig(os.path.join(CHARTS, "completeness.png"))
    plt.close(fig)

def chart_correctness(corr):
    order = sorted(PROVS, key=lambda p: corr[p]["right"])
    right = [corr[p]["right"] for p in order]
    wrong = [corr[p]["wrong"] for p in order]
    empty = [corr[p]["empty"] for p in order]
    labels = [LABEL[p] for p in order]
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    ax.barh(labels, right, color=RIGHT, label="Right person")
    ax.barh(labels, wrong, left=right, color=WRONG, label="Wrong (namesake)")
    ax.barh(labels, empty, left=[r + w for r, w in zip(right, wrong)], color=EMPTY, label="Empty")
    for i, p in enumerate(order):
        n = corr[p]["n"]
        ax.text(n + 4, i, f"{100*corr[p]['right']/n:.0f}% right", va="center", fontweight="bold")
    ax.set_xlim(0, 560)
    ax.set_xlabel("Profiles (n = 500)")
    ax.set_title("Correctness — is it the right person?", pad=24)
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=3,
              frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(os.path.join(CHARTS, "correctness.png"))
    plt.close(fig)

def chart_field_fill(fagg, cnt):
    pretty = {
        "full_name": "Name", "location": "Location", "headline": "Headline",
        "current_company": "Company", "current_title": "Title", "experience": "Experience",
        "exp_dates": "Exp. dates", "education": "Education", "recent_posts": "Posts",
        "post_engagement": "Post engmt.",
    }
    fields = FIELDS
    x = range(len(fields))
    width = 0.2
    fig, ax = plt.subplots(figsize=(11, 4.2))
    order = ["linkup", "perplexity", "exa", "parallel"]
    colors = {"linkup": LINKUP, "perplexity": "#7b61ff", "exa": "#f4a236", "parallel": "#9aa3ad"}
    for i, p in enumerate(order):
        vals = [100 * fagg[p][f] / cnt[p] for f in fields]
        ax.bar([xi + (i - 1.5) * width for xi in x], vals, width,
               label=LABEL[p], color=colors[p])
    ax.set_xticks(list(x))
    ax.set_xticklabels([pretty[f] for f in fields], rotation=30, ha="right")
    ax.set_ylim(0, 105)
    ax.set_ylabel("Fill rate (%)")
    ax.set_title("Per-field fill rate by provider")
    ax.legend(frameon=False, ncol=4, loc="upper center", bbox_to_anchor=(0.5, 1.0))
    fig.tight_layout()
    fig.savefig(os.path.join(CHARTS, "field_fill.png"))
    plt.close(fig)

def main():
    os.makedirs(CHARTS, exist_ok=True)
    comp, corr, fagg, cnt = compute()
    chart_completeness(comp)
    chart_correctness(corr)
    chart_field_fill(fagg, cnt)
    print(f"wrote charts to {CHARTS}/")

if __name__ == "__main__":
    main()
