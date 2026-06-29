import os
import numpy as np
from PIL import Image
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.offsetbox import OffsetImage, AnnotationBbox
from matplotlib.transforms import blended_transform_factory

OUT = os.path.dirname(os.path.abspath(__file__))
LOGODIR = os.path.join(OUT, "logos")

LINKUP = "#2F6BFF"
MUTED = "#D7DBE2"
INK = "#0F172A"
SUBTLE = "#94A3B8"

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Helvetica Neue", "Arial", "DejaVu Sans"],
    "figure.dpi": 200,
    "savefig.dpi": 200,
})

_LOGO_CACHE = {}

def logo(name, px=96):

    key = (name.lower(), px)
    if key in _LOGO_CACHE:
        return _LOGO_CACHE[key]
    img = Image.open(os.path.join(LOGODIR, f"{name.lower()}.png")).convert("RGBA")
    side = max(img.size)
    sq = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    sq.paste(img, ((side - img.width) // 2, (side - img.height) // 2))
    sq = sq.resize((px, px), Image.LANCZOS)
    arr = np.asarray(sq).astype(float) / 255.0
    _LOGO_CACHE[key] = arr
    return arr

def chart(fname, title, subtitle, data, suffix="", decimals=0):

    data = sorted(data, key=lambda x: x[1], reverse=True)
    labels = [d[0] for d in data]
    vals = [d[1] for d in data]
    colors = [LINKUP if l.lower() == "linkup" else MUTED for l in labels]

    fig, ax = plt.subplots(figsize=(7.2, 2.9))
    y = range(len(labels))
    ax.barh(y, vals, color=colors, height=0.62, zorder=3)
    ax.invert_yaxis()

    vmax = max(vals)
    for i, (l, v) in enumerate(zip(labels, vals)):
        txt = f"{v:.{decimals}f}{suffix}"
        ax.text(v + vmax * 0.015, i, txt, va="center", ha="left",
                fontsize=11, fontweight="bold" if l.lower() == "linkup" else "normal",
                color=INK if l.lower() == "linkup" else SUBTLE)

    ax.set_yticks([])
    blend = blended_transform_factory(ax.transAxes, ax.transData)
    for i, l in enumerate(labels):
        ab = AnnotationBbox(OffsetImage(logo(l), zoom=0.30), (-0.30, i),
                            xycoords=blend, frameon=False, box_alignment=(0, 0.5),
                            clip_on=False)
        ax.add_artist(ab)
        ax.text(-0.175, i, l, transform=blend, va="center", ha="left",
                fontsize=11, color=INK,
                fontweight="bold" if l.lower() == "linkup" else "normal")

    ax.set_xlim(0, vmax * 1.18)
    ax.set_xticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0)

    ax.text(-0.34, 1.30, title, transform=ax.transAxes, fontsize=13.5,
            fontweight="bold", color=INK, ha="left", va="bottom")
    ax.text(-0.34, 1.10, subtitle, transform=ax.transAxes, fontsize=10,
            color=SUBTLE, ha="left", va="bottom")

    fig.subplots_adjust(top=0.74, left=0.34, right=0.97, bottom=0.06)
    path = os.path.join(OUT, fname)
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote", path)

chart("people_enrichment.png",
      "Returned the correct person",
      "From a LinkedIn profile URL  ·  n=500  ·  % correct",
      [("Linkup", 94), ("Perplexity", 64), ("Parallel", 63), ("Exa", 56)],
      suffix="%")

chart("people_richness.png",
      "Pre-meeting brief quality",
      "Opus-4.8 judge, freshness + specificity + actionability  ·  n=100  ·  / 100",
      [("Linkup", 64.8), ("Parallel", 59.8), ("Exa", 55.8), ("Perplexity", 53.1)],
      decimals=1)

chart("people_freshness.png",
      "Caught a just-happened job change",
      "People who changed jobs this month  ·  n=~50  ·  % caught",
      [("Linkup", 74), ("Exa", 14), ("Parallel", 11), ("Perplexity", 9)],
      suffix="%")

chart("company_research.png",
      "Answer quality",
      "On-target sources  ·  company research, 100 companies \u00d7 5 sections (n=500)  ·  %",
      [("Linkup", 80.7), ("Exa", 76.8), ("Perplexity", 73.4), ("Parallel", 71.0)],
      suffix="%", decimals=1)

chart("company_funding.png",
      "Funding within \u00b125% of Crunchbase",
      "Total funding from name + HQ + year  ·  n=93  ·  % within band",
      [("Linkup", 83), ("Parallel", 74), ("Exa", 72), ("Perplexity", 56)],
      suffix="%")
