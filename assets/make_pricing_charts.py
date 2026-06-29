import os
import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = os.path.dirname(os.path.abspath(__file__))
INK = "#0F172A"
LINKUP_BLUE = "#2F6BFF"

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Helvetica Neue", "Arial", "DejaVu Sans"],
    "figure.dpi": 200,
    "savefig.dpi": 200,
})

ENGINES = ["Linkup", "Exa", "Parallel", "Perplexity"]
BENCHMARKS = ["Enrichment", "Richness", "Freshness", "Company research", "Funding"]
DATA = {
    "Enrichment":       [0.006, 0.007, 0.005, 0.008],
    "Richness":         [0.005, 0.017, 0.015, 0.005],
    "Freshness":        [0.006, 0.007, 0.005, 0.008],
    "Company research": [0.005, 0.007, 0.005, 0.005],
    "Funding":          [0.006, 0.007, 0.005, 0.008],
}
M = np.array([DATA[b] for b in BENCHMARKS])

VMIN, VMAX = 0.005, 0.009
CMAP = plt.get_cmap("RdYlGn_r")

fig, ax = plt.subplots(figsize=(7.8, 4.8))
im = ax.imshow(M, cmap=CMAP, aspect="auto", vmin=VMIN, vmax=VMAX)

ax.set_xticks(range(len(ENGINES)))
ax.set_xticklabels(ENGINES, fontsize=11.5, color=INK)
ax.get_xticklabels()[0].set_fontweight("bold")
ax.get_xticklabels()[0].set_color(LINKUP_BLUE)
ax.xaxis.set_ticks_position("top")
ax.set_yticks(range(len(BENCHMARKS)))
ax.set_yticklabels(BENCHMARKS, fontsize=10.5, color=INK)

for i in range(len(BENCHMARKS)):
    for j in range(len(ENGINES)):
        v = M[i, j]
        norm = min(1.0, max(0.0, (v - VMIN) / (VMAX - VMIN)))
        r, g, b, _ = CMAP(norm)
        lum = 0.299 * r + 0.587 * g + 0.114 * b
        tc = "white" if lum < 0.6 else INK
        ax.text(j, i, f"${v:.3f}", ha="center", va="center", fontsize=10.5,
                color=tc, fontweight="bold" if j == 0 else "normal")

ax.set_xticks(np.arange(-.5, len(ENGINES), 1), minor=True)
ax.set_yticks(np.arange(-.5, len(BENCHMARKS), 1), minor=True)
ax.grid(which="minor", color="white", linewidth=3)
ax.tick_params(which="both", length=0)
for s in ax.spines.values():
    s.set_visible(False)

ax.set_title("Cost per request ($) — greener = cheaper", fontsize=13.5,
             fontweight="bold", color=INK, pad=28, loc="left")

cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.03, ticks=[0.005, 0.007, 0.009])
cbar.ax.set_yticklabels(["$0.005", "$0.007", "$0.009+"], fontsize=9, color=INK)
cbar.outline.set_visible(False)
cbar.ax.tick_params(length=0)

fig.tight_layout()
path = os.path.join(OUT, "pricing.png")
fig.savefig(path, bbox_inches="tight", facecolor="white")
plt.close(fig)
print("wrote", path)
