import json, os
HERE = os.path.dirname(os.path.abspath(__file__))
c = json.load(open(os.path.join(HERE, "results", "scorecard.json")))
ENG = ["linkup", "exa", "perplexity", "parallel"]
order = sorted(ENG, key=lambda e: -c["engines"][e]["entity_relevance"])
print(f"\n=== COMPANY-RESEARCH BENCH (n={c['companies']}) ===\n")
hdr = ["engine", "signals/co", "info-rep%", "on-target%", "answers%", "right-co%", "P10"]
print("".join(f"{h:>12}" for h in hdr))
for e in order:
    d = c["engines"][e]
    mark = " *" if e == "linkup" else ""
    print(f"{e:>12}{d['items_per_company_deduped']:>12}{d['dup_rate_pct']:>11}%"
          f"{d['entity_relevance']:>11}%{d['topical_relevance']:>10}%{d['right_company_pct']:>10}%"
          f"{d['p10_relevance']:>9}{mark}")
print('''
Columns:
  signals/co  = Actionable signals found per company (distinct, deduped, across 5 sections)
  info-rep%   = Information repeated (duplicate rate among returned items)
  on-target%  = On-target sources (share of retrieved signals pointing at the target company)
  answers%    = Answers what was asked (share of signals addressing the section's question)
  right-co%   = Right company found (sections where the correct entity was identified)
  P10         = Worst-case consistency (relevance at the engine's worst 10% of companies)
''')
if "latency_ms" in c:
    print("=== LATENCY (per HTTP call, ms) ===")
    print(f"{'stage':22}{'n':>7}{'p50':>8}{'p95':>8}")
    for lab in sorted(c["latency_ms"]):
        d = c["latency_ms"][lab]
        print(f"{lab:22}{d['n']:>7}{d.get('p50_ms', d.get('median_ms', 0)):>8}{d['p95_ms']:>8}")
