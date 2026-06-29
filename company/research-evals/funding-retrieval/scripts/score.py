import argparse
import csv
import os
import re
import statistics

APIS = ["linkup", "exa", "perplexity", "parallel"]
HERE = os.path.dirname(os.path.abspath(__file__))

def parse_musd(s):

    if s is None:
        return None
    s = s.strip().replace(",", "")
    if s in ("", "—", "-", "N/A", "na"):
        return None
    m = re.match(r"^\$?\s*([0-9]*\.?[0-9]+)\s*([MBK]?)", s, re.IGNORECASE)
    if not m:
        return None
    val = float(m.group(1))
    unit = m.group(2).upper()
    if unit == "B":
        val *= 1000.0
    elif unit == "K":
        val /= 1000.0
    return val

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default=os.path.join(HERE, "..", "data", "golden_set.csv"))
    ap.add_argument("--out", default=os.path.join(HERE, "..", "results", "scorecard_recomputed.csv"))
    ap.add_argument("--reference", default="",
                    help="optional: also require this engine to have returned a number "
                         "(default: empty = score every row with a golden value, no engine-specific cut)")
    args = ap.parse_args()

    with open(args.inp, newline="") as f:
        rows = list(csv.DictReader(f))

    # The scored set is defined solely by golden-value availability — independent of any
    # engine. Coverage then reports the share of that set each engine returned a number for;
    # blanks count as misses for every engine (fixed denominator n below).
    subset = [r for r in rows
              if parse_musd(r["golden"]) is not None
              and (not args.reference or parse_musd(r[args.reference]) is not None)]
    n = len(subset)

    cards = []
    for api in APIS:
        errors = []
        within = {10: 0, 25: 0, 50: 0}
        returned = 0
        for r in subset:
            golden = parse_musd(r["golden"])
            val = parse_musd(r[api])
            if val is None:
                continue
            returned += 1
            err = abs(val - golden) / golden
            errors.append(err)
            for band in within:
                if err <= band / 100.0:
                    within[band] += 1
        cards.append({
            "api": api,
            "within_10": round(100 * within[10] / n),
            "within_25": round(100 * within[25] / n),
            "within_50": round(100 * within[50] / n),
            "median_err": round(100 * statistics.median(errors)) if errors else "",
            "coverage": round(100 * returned / n),
            "n": n,
        })

    cards.sort(key=lambda c: c["within_25"], reverse=True)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    fields = ["api", "within_10", "within_25", "within_50", "median_err", "coverage", "n"]
    with open(args.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(cards)

    scope = f"golden present and {args.reference} returned" if args.reference else "every company with a golden value"
    print(f"Scored n={n} ({scope}); blanks count as misses\n")
    hdr = f"{'API':<12}{'≤10%':>7}{'≤25%':>7}{'≤50%':>7}{'median':>8}{'cover':>7}"
    print(hdr)
    print("-" * len(hdr))
    for c in cards:
        print(f"{c['api']:<12}{c['within_10']:>6}%{c['within_25']:>6}%"
              f"{c['within_50']:>6}%{str(c['median_err'])+'%':>8}{c['coverage']:>6}%")
    print(f"\nWrote {args.out}")

if __name__ == "__main__":
    main()
