# Linkup GTM Benchmarks

Public, reproducible benchmarks of how well web-search APIs handle real production
GTM work. We compare the major players on the market — **Linkup, Exa, Perplexity,
and Parallel** — across the two use cases at the core of every modern GTM motion:

- **People** — pull correct, current, and rich information about a person from the
  open web: the data behind enrichment, lead scoring, and signal detection.
- **Company** — research a company end to end: the firmographics and signal that
  drive account scoring, prioritization, and outbound.

Each benchmark ships its dataset, the exact queries, the scoring code, and the
results, so every number here can be re-run and re-checked.

**Why this exists.** A search API is increasingly the retrieval layer behind CRM
enrichment, pre-call research, lead scoring, signal detection, and many other
AI-native workflows. The usual benchmarks for these APIs measure generic QA; these
measure the GTM jobs: given a person, return *that* person; given a company, return
information a rep can act on.

---

## Linkup across GTM tasks

Two benchmarks, scored across all four engines. Higher is better unless noted.

### People

| Signal         | What it measures                                                                       | Linkup   | Exa  | Perplexity | Parallel |
| -------------- | -------------------------------------------------------------------------------------- | -------- | ---- | ---------- | -------- |
| **Enrichment** | Returned the **correct and complete information about a person** from LinkedIn (n=500) | **94%**  | 56%  | 64%        | 63%      |
| **Richness**   | Real-time, current activity about a person from across the web, 0–100 (n=100)          | **64.8** | 55.8 | 53.1       | 59.8     |
| **Freshness**  | Caught a **just-happened signal** (example tracked: job change) (n=~50)                  | **74%**  | 14%  | 9%         | 11%      |

### Company

| Signal               | What it measures                                            | Linkup    | Exa   | Perplexity | Parallel |
| -------------------- | ---------------------------------------------------------- | --------- | ----- | ---------- | -------- |
| **Answer quality**   | Share of retrieved sources **on-target** for the company (search-only, 100 companies × 5 sections, n=500) | **80.7%** | 76.8% | 73.4%      | 71.0%    |
| **Funding accuracy** | Total funding within **±25%** of Crunchbase (n=93)          | **83%**   | 72%   | 56%        | 74%      |

---

## People

Three signals that cover the people-data lifecycle:

1. Getting the record right
2. Turning it into something useful
3. Keeping it current

### Signal 1 — Enrichment success rate *(completeness + correctness, n=500)*

We hand each API a LinkedIn profile URL and ask for the full profile via its native
structured-output endpoint. Two deterministic checks against an independent
ground-truth DB: *how much came back*, and *is it the right person?*

| Engine     | Fields filled (completeness /100) | Correct person (%) | Wrong person / namesake (of 500) |
| ---------- | --------------------------------- | ------------------ | -------------------------------- |
| **Linkup** | **96.5**                          | **94%**            | **12**                           |
| Perplexity | 73.7                              | 64%                | 122                              |
| Exa        | 71.9                              | 56%                | 191                              |
| Parallel   | 60.5                              | 63%                | 69                               |

![Returned the correct person, by engine](assets/people_enrichment.png)

Completeness and correctness are different questions: an engine can fill the *name*
box confidently while attaching the wrong human's company. Because correctness is
checked against an independent DB, the gap measures the thing downstream automation
depends on — whether the record points at the right account before a rep ever sees it.

**Where this matters in GTM:** CRM enrichment and data hygiene, lead routing and
scoring, identity resolution and dedupe, and clean list/TAM building — all of which
depend on a record that's both filled *and* pointed at the right person.

### Signal 2 — Richness of content *(e.g. pre-meeting brief quality, n=100)*

A different task from extraction: each engine's raw web results are synthesized into
a short sales brief (notes + conversation questions), then scored by an Opus-4.8
judge on freshness + specificity + actionability.

| Engine     | Brief score (overall /100) | Freshness | Specificity | Actionability | Best brief (of 100) |
| ---------- | -------------------------- | --------- | ----------- | ------------- | ------------------- |
| **Linkup** | **64.8**                   | **58.6**  | 69.4        | **68.2**      | **51**              |
| Parallel   | 59.8                       | 45.9      | 70.1        | 64.9          | 26                  |
| Exa        | 55.8                       | 43.9      | 66.0        | 59.9          | 16                  |
| Perplexity | 53.1                       | 42.6      | 59.7        | 58.1          | 6                   |

![Pre-meeting brief quality, by engine](assets/people_richness.png)

**Where this matters in GTM:**

- **Account research before a call** — a rep needs a brief, not a raw field dump.
- **Freshness is the differentiator** — a post from last week or a just-announced round preps a rep better than a 2019 job title.

### Signal 3 — Freshness of people content *(job-change detection, n=~50)*

We took a subset of people who changed jobs **this month** and asked each engine for
their current employer — does it report the **new** company or the **stale** old one?

> *Note: a small share of these are internal moves — a new role at the same company — not just company-to-company changes.*

| Engine     | Caught the move (fresh %) | Reported stale employer | Wrong person | No answer |
| ---------- | ------------------------- | ----------------------- | ------------ | --------- |
| **Linkup** | **74%**                   | 7                       | 4            | 4         |
| Exa        | 14%                       | 32                      | 11           | 6         |
| Parallel   | 11%                       | 30                      | 11           | 10        |
| Perplexity | 9%                        | 17                      | 7            | 28        |

![Caught a just-happened job change, by engine](assets/people_freshness.png)

**Where this matters in GTM:**

- **Highest-value trigger** — a champion who just moved may buy again, but only if the signal is fresh.
- **The failure mode is *stale*** — the right person, reported at their previous company.
- **Judged, not string-matched** — an Opus-4.8 model classifies across languages and abbreviations.

---

## Company

Firmographics and research that drive account scoring, prioritization, and outbound.
Two signals are live; more are in progress.

### Signal 1 — B2B company research *(search-only · 100 companies × 5 sections, n=500)*

Each engine researches a company with **one search endpoint, no chaining and no
extract** — the fair single-primitive comparison (Linkup `/v1/search`, Exa `/search`
with highlights, Perplexity & Parallel Search APIs; Exa uses highlights rather than
full-page contents, so no engine gets a free extract step). Across 100 companies, the
pipeline is held identical across engines so the result reflects *retrieval*, not the
writer:

1. **Search** — each engine runs the section's queries through its single search endpoint, returning snippets only.
2. **Synthesize** (`claude-sonnet-4-6`) — one shared prompt structures each engine's results, grounded *only* in what it returned.
3. **Judge** (`claude-opus-4-8`) — scores each section against the company's **verified identity** for right-company, on-target sources, and answering the ask.

The five sections — what each set of queries goes after, and why it's GTM signal:

| Section             | What the queries target                                   | Why it matters                                            |
| ------------------- | --------------------------------------------------------- | --------------------------------------------------------- |
| **Offering**        | *"what does {company} do / product"*                      | the core pitch: what they sell and to whom                |
| **Pain → solution** | *features / benefits* + *pain point / problem / solution* | maps buyer problems to the product angle a rep leads with |
| **Case studies**    | *case study / success story / ROI / metrics*              | proof points: customer + key result                       |
| **Customers**       | *customer / client / "trusted by" / partnership*          | named logos and partners for account mapping              |
| **CTAs**            | site-scoped *book a demo / pricing / sign up*             | the buying motion and conversion signals                  |

| Engine     | Answer quality (on-target) | Answered the ask | Right company | Info repeated | Worst-case (P10) |
| ---------- | -------------------------- | ---------------- | ------------- | ------------- | ---------------- |
| **Linkup** | **80.7%**                  | **76.8%**        | **83%**       | 5%            | **57.7**         |
| Exa        | 76.8%                      | 73.0%            | 80%           | 10%           | 56.0             |
| Perplexity | 73.4%                      | 68.5%            | 76%           | 3%            | 53.7             |
| Parallel   | 71.0%                      | 66.1%            | 73%           | 12%           | 39.7             |

![Answer quality (on-target sources), by engine](assets/company_research.png)

Only relevance and identification use the judge; info-repeated and worst-case
consistency (P10) are computed deterministically. Relevance composite = mean over the
5 sections of (entity + topical relevance) / 2.

**Where this matters in GTM:**

- **Account research at scale** — more on-target signal per company, steady even on hard accounts.
- **Territory & ICP planning** — segment target lists from accurate offering and customer data.
- **Outbound personalization** — pain → solution pairings and case studies a rep can drop into a sequence.

### Signal 2 — Funding retrieval *(n=93)*

Given only a company's **name + HQ + founding year**, return total funding raised via
each engine's structured output. Scored against Crunchbase total equity funding;
`error = |api − golden| / golden`.

| Engine     | Within 10% | Within 25% | Within 50% | Median error | Coverage |
| ---------- | ---------- | ---------- | ---------- | ------------ | -------- |
| **Linkup** | **63%**    | **83%**    | **90%**    | **2%**       | 100%     |
| Parallel   | 57%        | 74%        | 82%        | 7%           | 100%     |
| Exa        | 48%        | 72%        | 86%        | 10%          | 100%     |
| Perplexity | 43%        | 56%        | 70%        | 15%          | 94%      |

![Funding within ±25% of Crunchbase, by engine](assets/company_funding.png)

All four engines are scored on the same set — the 93 companies that have a verified
Crunchbase total-funding value — chosen independently of any engine's output. Coverage is
the share of that set each engine returned a number for; blanks count as misses for every
engine (fixed denominator), so no engine is flattered by abstaining.

**Where this matters in GTM:**

- **ICP fit & account scoring** — funding stage and total raised are core qualification inputs.
- **Timing & prioritization** — recently funded accounts have budget; the real number (not the ballpark) is what makes it usable in a scoring model.

---

## Cost per request

Every API here is priced **per request** (the search endpoints carry no token bill).
Full pricing below — **greener = cheaper** in the matrix.

| Benchmark | **Linkup** | Exa | Parallel | Perplexity |
| ---------------------- | ---------- | ------ | -------- | ---------- |
| Enrichment             | **$0.006** | $0.007 | $0.005   | $0.008     |
| Richness *(20 results)* | **$0.005** | $0.017 | $0.015   | $0.005     |
| Freshness              | **$0.006** | $0.007 | $0.005   | $0.008     |
| Company research       | **$0.005** | $0.007 | $0.005   | $0.005     |
| Funding                | **$0.006** | $0.007 | $0.005   | $0.008     |

![Cost per request, by benchmark and engine](assets/pricing.png)

- **Linkup is flat — never above $0.006/request**, sourced ($0.005) or structured ($0.006), no matter how many results come back.
- **Linkup never charges per source.** Exa and Parallel bill **per result above 10**, so they get more expensive the more a query returns.
- **The gap is widest when results scale:** on the 20-result richness task, Linkup is **$0.005 vs Exa $0.017 and Parallel $0.015 — 3×+ cheaper**.
- **More budget doesn't close the quality gap.** Even maxed out at `numResults=100` (~**$0.097/request, ~16× Linkup**), Exa's enrichment was **56% correct vs Linkup's 94%** at $0.006 — and freshness **14% vs 74%**. Linkup wins on quality *and* cost. *(The matrix normalizes Exa to 10 results for a fair per-request comparison; this is the engine's own 100-result run.)*

> List prices, June 2026, per request. Exa enrichment/freshness normalized to 10 results
> for an apples-to-apples comparison (source runs used 100); richness keeps 20 results,
> which every engine used. Parallel funding assumes the `lite-fast` processor; Perplexity's
> structured extract is a base-Sonar request fee plus a sub-penny token cost.

---

## Methodology

The benches differ in task, but share the same design principles — built to be
reproducible and to reward signal a GTM team can actually use, not raw volume.

- **Each API at its own native surface.** Extraction uses structured-output
  endpoints; research uses raw search endpoints. No LLM wrapper sits between the API
  and the score, so we measure the retrieval engine itself. Where a step *does* need a
  model (synthesizing a brief, structuring research), it's held **identical across all
  four engines** so differences reflect retrieval, not the writer.
- **Independent ground truth.** People correctness joins to a profile DB not derived
  from any of the four APIs; funding checks against Crunchbase; company research is
  anchored on a verified company identity.
- **Deterministic where possible, judged where necessary.** Field-fill, company-match,
  dedup, source-mix, and consistency are computed deterministically. An LLM judge is
  used only where strings fail — cross-language company names, and the quality of a
  brief or a research answer.
- **Judged for business signal, not volume.** The judge rubrics deliberately reward
  what a rep needs — *fresh, specific, on-target, and actionable* — and penalize
  padding, namesakes, and stale or fabricated detail. A long answer full of generic or
  duplicated points scores worse than a short one that's correct and current.
- **Reproducible.** Datasets, queries, and scoring scripts are committed; the company
  bench even ships its captured retrieval so you can rebuild the scorecard with zero
  API calls. Search is non-deterministic, so committed numbers are one representative
  run.

---

## Repo layout

```
Linkup-GTM-benchmarks/
├── README.md                    # this file — the single combined narrative
├── people/                      # LinkedIn profile extraction — 3 signals (n=500)
└── company/
    ├── research-100/            # B2B company research — search-only, 100 companies × 5 sections (n=500)
    └── research-evals/          # funding retrieval (+ future company evals)
```

Each folder is self-contained — its own data and scripts. This top-level README is the
single source for the combined story, results, and reproduction steps.

```bash
git clone https://github.com/shauryajain21/Linkup-GTM-benchmarks.git
cd Linkup-GTM-benchmarks

# People — enrichment, richness, freshness (cached judge verdicts; no API key needed)
cd people && pip install -r requirements.txt
python3 eval.py                 # Pillar 1: enrichment (completeness + correctness)
python3 eval_meeting_briefs.py  # Pillar 2: brief quality (from cached verdicts)
python3 eval_freshness.py       # Pillar 3: job-change freshness (from cached verdicts)
python3 make_charts.py          # charts

# Company research (search-only) — rebuilds from captured retrieval/synth/judge, zero API calls
cd ../company/research-100 && pip install -r requirements.txt
python3 run_bench.py --search-only --companies data/companies_100.json --aggregate && python3 report.py

# Funding retrieval — scores the committed golden set
cd ../research-evals/funding-retrieval && pip install -r requirements.txt
python3 scripts/score.py && python3 scripts/plot_results.py
```

To re-run the people evals live (fresh API calls) or re-judge, copy
`people/.env.example` to `.env`, add keys, and pass `--rejudge`. The company bench rebuilds
its scorecard from committed retrieval/synth/judge with `run_bench.py --aggregate` (zero API
calls), or re-runs live with the 5 keys in `company/research-100/.env.example`.

---

## Caveats

- **Search is non-deterministic.** Re-runs shift a few values; committed numbers are
  one representative run.
- **Targeted sets where noted.** Some signals use focused subsets by design — e.g. the
  job-change test is built from people who changed roles that month. Each bench's exact
  set and method are documented in this README and in its scripts' docstrings.
- **Transparent and reproducible.** These are vendor benchmarks built by Linkup; the
  method, data, and scoring are fully open so every result can be independently re-run
  and verified rather than taken on faith.
