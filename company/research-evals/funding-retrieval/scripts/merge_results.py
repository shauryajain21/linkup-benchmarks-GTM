import argparse
import csv
import glob
import os
import sys

PROVIDER_ORDER = {"linkup": 0, "exa": 1, "perplexity": 2, "parallel": 3}
FIELDS = ["provider", "endpoint", "query", "response", "params"]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="results", help="dir holding <provider>.csv partials")
    ap.add_argument("--out", default="query_results.csv", help="combined output path")
    args = ap.parse_args()

    partials = sorted(glob.glob(os.path.join(args.dir, "*.csv")))
    partials = [p for p in partials if os.path.abspath(p) != os.path.abspath(args.out)]
    if not partials:
        sys.exit(f"No partial CSVs found in {args.dir}/")

    rows = []
    for path in partials:
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                rows.append({k: row.get(k, "") for k in FIELDS})

    rows.sort(key=lambda r: (r["query"], PROVIDER_ORDER.get(r["provider"], 99), r["endpoint"]))

    with open(args.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    providers = sorted({r["provider"] for r in rows})
    print(f"Merged {len(partials)} partials -> {args.out}: "
          f"{len(rows)} rows across {providers}", file=sys.stderr)

if __name__ == "__main__":
    main()
