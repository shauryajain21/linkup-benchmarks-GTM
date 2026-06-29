import argparse, asyncio, csv, json, os, re, sys, time
from collections import defaultdict

import httpx

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "results")
DB = os.path.join(HERE, "data", "companies_150.csv")
RAW, SYNTH, JUDGE = (os.path.join(OUT, f) for f in ("raw.jsonl", "synth.jsonl", "judge.jsonl"))
SEARCH_ONLY = False
SCORECARD = os.path.join(OUT, "scorecard.json")
ENGINES = ["linkup", "exa", "perplexity", "parallel"]
SYNTH_MODEL, JUDGE_MODEL = "claude-sonnet-4-6", "claude-opus-4-8"
SYNTH_MAX, JUDGE_MAX = 16000, 4000
csv.field_size_limit(10 ** 8)

RATES = {"linkup": 25.0, "exa": 10.0, "perplexity": 10.0, "parallel": 10.0, "anthropic": 10.0}
TIMINGS = []

def load_env():
    p = os.path.join(HERE, ".env")
    if os.path.exists(p):
        for line in open(p):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1); os.environ.setdefault(k.strip(), v.strip())
load_env()
KEYS = {e: os.environ.get(f"{e.upper()}_API_KEY", "") for e in ENGINES}
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

SECTIONS = {
    "1_offering": {
        "searches": ['"{name}" {domain} what does company do product'],
        "scrape": True,
        "synth": ("Extract the company's offering as discrete bullets — as many distinct points as are "
                  "grounded (what they sell, who they sell to, value propositions, key capabilities). "
                  "One point per bullet. Do not cap the number."),
        "schema": {"type": "object", "properties": {"offering_points": {"type": "array", "items": {"type": "string"}}},
                   "required": ["offering_points"], "additionalProperties": False},
        "list_key": "offering_points",
    },
    "2_features": {
        "searches": ['"{name}" {domain} features benefits product',
                     '"{name}" {domain} "pain point" OR problem OR challenge OR solution'],
        "scrape": True,
        "synth": ("Extract Pain Point / Solution pairings: for each give pain_point (the buyer problem, in "
                  "the website's language), solution (how the product solves it), feature (the feature name "
                  "as stated). Extract as many GROUNDED pairings as the content supports — no cap, no "
                  "extrapolation, never invent generic pairings."),
        "schema": {"type": "object", "properties": {"pairings": {"type": "array", "items": {"type": "object",
                   "properties": {"pain_point": {"type": "string"}, "solution": {"type": "string"}, "feature": {"type": "string"}},
                   "required": ["pain_point", "solution", "feature"], "additionalProperties": False}}},
                   "required": ["pairings"], "additionalProperties": False},
        "list_key": "pairings",
    },
    "3_case_studies": {
        "searches": ['"{name}" {domain} case study OR success story OR customer story',
                     '"{name}" {domain} results metrics ROI'],
        "scrape": True,
        "synth": ("Find case studies / success / customer stories. Return each with its URL, the customer "
                  "name, and one key result metric. If none exist in the results, set exists=false."),
        "schema": {"type": "object", "properties": {"exists": {"type": "boolean"}, "case_studies": {"type": "array",
                   "items": {"type": "object", "properties": {"url": {"type": "string"}, "customer": {"type": "string"},
                   "key_result": {"type": "string"}}, "required": ["url", "customer", "key_result"], "additionalProperties": False}}},
                   "required": ["exists", "case_studies"], "additionalProperties": False},
        "list_key": "case_studies",
    },
    "4_customers": {
        "searches": ['"{name}" {domain} customer OR client OR "powered by" OR "built with" OR testimonial',
                     '"{name}" {domain} partnership OR "works with" OR integration OR client'],
        "scrape": True,
        "synth": ("Return named customers/clients with their main website URL. Only include ones you "
                  "actually found in the results — do not guess URLs, do not invent customers."),
        "schema": {"type": "object", "properties": {"customers": {"type": "array", "items": {"type": "object",
                   "properties": {"name": {"type": "string"}, "url": {"type": "string"}},
                   "required": ["name", "url"], "additionalProperties": False}}},
                   "required": ["customers"], "additionalProperties": False},
        "list_key": "customers",
    },
    "5_ctas": {
        "searches": ['site:{domain} "book a demo" OR "get started" OR "request pricing" OR "contact sales" OR "sign up" OR "try free"',
                     '"{name}" {domain} pricing demo signup'],
        "scrape": True,
        "synth": ("Extract every call-to-action (CTA) button/link evident in the results — header/nav, hero, "
                  "pricing, footer. For each return the exact text, destination URL, and location. Include all."),
        "schema": {"type": "object", "properties": {"ctas": {"type": "array", "items": {"type": "object",
                   "properties": {"text": {"type": "string"}, "url": {"type": "string"}, "location": {"type": "string"}},
                   "required": ["text", "url", "location"], "additionalProperties": False}}},
                   "required": ["ctas"], "additionalProperties": False},
        "list_key": "ctas",
    },
}

def load_companies(limit=None, offset=0):
    cols = ["name", "domain", "url", "hq", "founded", "funding_status",
            "total_funding_usd", "last_round", "investors", "crunchbase"]
    rows = json.load(open(DB)) if DB.endswith(".json") else list(csv.DictReader(open(DB)))
    out = [{k: str(r.get(k) or "").strip() for k in cols} for r in rows]
    out = [c for c in out if c["name"] and c["domain"]]
    out = out[offset:]
    if limit:
        out = out[:limit]
    return out

def disambig_block(c):
    lines = [f"TARGET COMPANY (use this to identify the EXACT entity and reject same-named namesakes):",
             f"- Name: {c['name']}",
             f"- Website: {c['url']}  (domain: {c['domain']})",
             f"- Headquarters: {c['hq'] or 'n/a'}",
             f"- Founded: {c['founded'] or 'n/a'}"]
    fund = c["funding_status"] or "n/a"
    if c["total_funding_usd"]:
        fund += f"; total raised ~${c['total_funding_usd']} USD"
    if c["last_round"]:
        fund += f"; latest round: {c['last_round']}"
    lines.append(f"- Funding: {fund}")
    if c["investors"]:
        lines.append(f"- Lead investors: {c['investors']}")
    if c["crunchbase"]:
        lines.append(f"- Crunchbase: {c['crunchbase']}")
    return "\n".join(lines)

def render_searches(sec, c):
    return [q.format(name=c["name"], domain=c["domain"]) for q in SECTIONS[sec]["searches"]]

NEWS = ("techcrunch", "forbes", "bloomberg", "reuters", "businesswire", "prnewswire", "venturebeat",
        "theinformation", "axios", "cnbc", "wsj", "ft.com", "sifted", "fortune", "geekwire")
AGG = ("getlatka", "latka", "tracxn", "pitchbook", "growjo", "cbinsights", "owler", "rocketreach", "zoominfo")

class Rate:

    def __init__(self, qps):
        self.interval = 1.0 / qps if qps > 0 else 0.0
        self.lock = asyncio.Lock()
        self.next = 0.0
    async def acquire(self):
        async with self.lock:
            now = asyncio.get_event_loop().time()
            start = max(now, self.next)
            self.next = start + self.interval
            delay = start - now
        if delay > 0:
            await asyncio.sleep(delay)

async def _post(client, url, headers, body, timeout=90, rate=None, label=None):
    for attempt in range(4):
        try:
            if rate:
                await rate.acquire()
            t0 = time.perf_counter()
            r = await client.post(url, headers=headers, json=body, timeout=timeout)
            ms = (time.perf_counter() - t0) * 1000
            if r.status_code in (429, 500, 502, 503, 529):
                await asyncio.sleep(2 ** attempt); continue
            r.raise_for_status()
            if label: TIMINGS.append([label, round(ms, 1)])
            return r.json()
        except Exception as e:
            if attempt == 3:
                return {"_error": f"{type(e).__name__}: {str(e)[:200]}"}
            await asyncio.sleep(2 ** attempt)
    return {"_error": "exhausted retries"}

def _fmt_results(results):

    lines, urls = [], []
    for it in results or []:
        if not isinstance(it, dict):
            continue
        title = it.get("title") or it.get("name") or ""
        url = it.get("url") or it.get("id") or ""
        body = it.get("text") or it.get("snippet") or it.get("content") or ""
        if not body and it.get("highlights"):
            body = " ".join(it["highlights"]) if isinstance(it["highlights"], list) else str(it["highlights"])
        if not body and it.get("excerpts"):
            body = " ".join(it["excerpts"]) if isinstance(it["excerpts"], list) else str(it["excerpts"])
        if url:
            urls.append(url)
        lines.append(f"### {title}\n{url}\n{body}".strip())
    return "\n\n".join(lines), urls

async def retrieve(client, engine, sec, c, rate):

    queries = render_searches(sec, c)
    scrape = SECTIONS[sec]["scrape"] and not SEARCH_ONLY
    blob_parts, urls, errors = [], [], []

    async def collect(label, coro):
        r = await coro
        if isinstance(r, dict) and "_error" in r:
            errors.append(f"{label}: {r['_error']}"); return
        if engine == "linkup":
            if "results" in r:
                t, u = _fmt_results(r["results"]); blob_parts.append(t); urls.extend(u)
            elif "markdown" in r:
                blob_parts.append(f"### [scraped page] {c['url']}\n{r['markdown']}"); urls.append(c["url"])
        elif engine == "exa":
            if "results" in r:
                t, u = _fmt_results(r["results"]); blob_parts.append(t); urls.extend(u)
        elif engine == "perplexity":
            res = r.get("results") or r.get("search_results") or []
            t, u = _fmt_results(res); blob_parts.append(t); urls.extend(u)
        elif engine == "parallel":
            t, u = _fmt_results(r.get("results") or []); blob_parts.append(t); urls.extend(u)

    tasks = []
    if engine == "linkup":
        h = {"Authorization": f"Bearer {KEYS['linkup']}"}
        for q in queries:
            tasks.append(collect(f"search:{q[:30]}", _post(client, "https://api.linkup.so/v1/search",
                         h, {"q": q, "depth": "standard", "outputType": "searchResults"}, rate=rate, label="retrieve:"+engine)))
        if scrape:
            tasks.append(collect("scrape", _post(client, "https://api.linkup.so/v1/fetch", h, {"url": c["url"]}, rate=rate, label="retrieve:"+engine)))
    elif engine == "exa":
        h = {"x-api-key": KEYS["exa"]}
        for q in queries:
            tasks.append(collect(f"search:{q[:30]}", _post(client, "https://api.exa.ai/search",
                         h, {"query": q, "type": "auto", "numResults": 10,
                             "contents": {"highlights": True} if SEARCH_ONLY else {"text": True}}, rate=rate, label="retrieve:"+engine)))
        if scrape:
            tasks.append(collect("scrape", _post(client, "https://api.exa.ai/contents",
                         h, {"urls": [c["url"]], "text": True}, rate=rate, label="retrieve:"+engine)))
    elif engine == "perplexity":
        h = {"Authorization": f"Bearer {KEYS['perplexity']}"}
        for q in queries:
            tasks.append(collect(f"search:{q[:30]}", _post(client, "https://api.perplexity.ai/search",
                         h, {"query": q, "max_results": 10}, rate=rate, label="retrieve:"+engine)))
    elif engine == "parallel":
        h = {"x-api-key": KEYS["parallel"]}
        for q in queries:
            tasks.append(collect(f"search:{q[:30]}", _post(client, "https://api.parallel.ai/v1/search",
                         h, {"objective": q, "search_queries": [q], "mode": "advanced"}, rate=rate, label="retrieve:"+engine)))
    await asyncio.gather(*tasks)
    return {"raw": "\n\n".join(p for p in blob_parts if p), "urls": urls, "errors": errors}

async def anthropic_call(client, model, system, user, max_tokens, rate=None, label=None):
    body = {"model": model, "max_tokens": max_tokens, "system": system,
            "messages": [{"role": "user", "content": user}]}
    h = {"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    r = await _post(client, "https://api.anthropic.com/v1/messages", h, body, timeout=180, rate=rate, label=label)
    if "_error" in r:
        return f"ERROR {r['_error']}"
    try:
        return "".join(b.get("text", "") for b in r.get("content", []) if b.get("type") == "text")
    except Exception:
        return json.dumps(r)[:500]

def parse_json(t):
    t = (t or "").strip()
    try:
        return json.loads(t)
    except Exception:
        m = re.search(r"\{.*\}", t, re.S)
        try:
            return json.loads(m.group(0)) if m else None
        except Exception:
            return None

SYNTH_SYS = ("You are an expert B2B marketing researcher. You are given a TARGET company (with identifying "
             "details) and a block of RAW web results an engine gathered. Use ONLY information present in the "
             "raw results — no outside or prior knowledge, never invent. Only include items that clearly "
             "concern the TARGET company at its domain; ignore content about a different, same-named company.\n\n"
             "TASK: {task}\n\nReturn ONLY JSON matching this schema (no prose): {schema}")

async def synth(client, sec, c, raw, rate=None):
    sysmsg = SYNTH_SYS.format(task=SECTIONS[sec]["synth"], schema=json.dumps(SECTIONS[sec]["schema"]))
    user = f"{disambig_block(c)}\n\nRAW WEB RESULTS (the ONLY information you may use):\n{raw}"
    out = await anthropic_call(client, SYNTH_MODEL, sysmsg, user, SYNTH_MAX, rate=rate, label="synth")
    obj = parse_json(out)
    return obj if isinstance(obj, dict) else {"_parse_failed": out[:300]}

JUDGE_SYS = ("You judge how RELEVANT an engine's retrieved company-research answer is to a SPECIFIC target "
             "company. You are given the verified target (name, domain, HQ, founded, funding, investors) and, "
             "for each engine, the structured items it returned for one section. For EACH engine score:\n"
             "- right_company (bool): do the items clearly describe the TARGET entity at that domain (consistent "
             "with its HQ / founding / investors), NOT a same-named different company? Empty answer => false.\n"
             "- entity_relevance (0-100): share of the returned items that are actually about the target entity "
             "(not a namesake / not generic).\n"
             "- topical_relevance (0-100): share of the items that genuinely answer this section's question.\n"
             "- note: one short phrase.\n"
             "Be strict; an answer about the wrong same-named company scores entity_relevance low and "
             "right_company=false. Spread the scores.")

async def judge_group(client, sec, c, answers, rate=None):
    schema = {"type": "object", "properties": {e: {"type": "object", "properties": {
        "right_company": {"type": "boolean"}, "entity_relevance": {"type": "integer"},
        "topical_relevance": {"type": "integer"}, "note": {"type": "string"}},
        "required": ["right_company", "entity_relevance", "topical_relevance", "note"],
        "additionalProperties": False} for e in ENGINES}, "required": ENGINES, "additionalProperties": False}
    payload = {"target": {k: c[k] for k in ("name", "domain", "url", "hq", "founded", "funding_status", "investors")},
               "section": sec, "engine_answers": answers}
    user = json.dumps(payload, ensure_ascii=False)[:120000] + "\n\nReturn ONLY JSON matching:\n" + json.dumps(schema)
    out = await anthropic_call(client, JUDGE_MODEL, JUDGE_SYS, user, JUDGE_MAX, rate=rate, label="judge")
    obj = parse_json(out)
    return obj if isinstance(obj, dict) else {"_parse_failed": out[:300]}

_locks = {}
def _lock(path):
    _locks.setdefault(path, asyncio.Lock()); return _locks[path]
def load_keys(path):
    import gzip
    if os.path.exists(path):
        fh = open(path)
    elif os.path.exists(path + ".gz"):
        fh = gzip.open(path + ".gz", "rt")
    else:
        return {}
    d = {}
    with fh:
        for line in fh:
            try:
                o = json.loads(line); d[o["key"]] = o
            except Exception:
                pass
    return d
async def append(path, obj):
    async with _lock(path):
        with open(path, "a") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")

async def run(companies, concurrency):
    raw_done, synth_done, judge_done = load_keys(RAW), load_keys(SYNTH), load_keys(JUDGE)

    rates = {p: Rate(q) for p, q in RATES.items()}
    gsem = asyncio.Semaphore(concurrency)
    stats = defaultdict(int)
    async with httpx.AsyncClient() as client:
        async def unit(c, sec, engine):
            key = f"{c['name']}|{sec}|{engine}"
            if key not in raw_done:
                rr = await retrieve(client, engine, sec, c, rates[engine])
                rec = {"key": key, "company": c["name"], "section": sec, "engine": engine,
                       "raw": rr["raw"], "urls": rr["urls"], "errors": rr["errors"]}
                await append(RAW, rec); raw_done[key] = rec; stats["retrieved"] += 1
            if key not in synth_done:
                raw = raw_done[key]["raw"]
                structured = await synth(client, sec, c, raw, rates["anthropic"])
                rec = {"key": key, "company": c["name"], "section": sec, "engine": engine,
                       "structured": structured}
                await append(SYNTH, rec); synth_done[key] = rec; stats["synthed"] += 1
            return synth_done[key]["structured"]

        async def group(c, sec):
            async with gsem:
                gkey = f"{c['name']}|{sec}"
                res = await asyncio.gather(*[unit(c, sec, e) for e in ENGINES])
                answers = {e: a for e, a in zip(ENGINES, res)}
                if gkey not in judge_done:
                    verdict = await judge_group(client, sec, c, answers, rates["anthropic"])
                    await append(JUDGE, {"key": gkey, "company": c["name"], "section": sec, "verdict": verdict})
                    stats["judged"] += 1
                    print(f"  judged {gkey}  (retrieved={stats['retrieved']} synthed={stats['synthed']})", flush=True)

        await asyncio.gather(*[group(c, sec) for c in companies for sec in SECTIONS])
    print(f"\nDONE  retrieved={stats['retrieved']} synthed={stats['synthed']} judged={stats['judged']}")
    if TIMINGS:
        with open(os.path.join(OUT, "timings.jsonl"), "a") as f:
            for lab, ms in TIMINGS:
                f.write(json.dumps({"label": lab, "ms": ms}) + "\n")
    print(f"stores: {RAW} | {SYNTH} | {JUDGE}  | timings: {len(TIMINGS)} calls")

def classify(url, domain):
    u = (url or "").lower()
    if domain and domain.lower() in u:
        return "own_site"
    if "linkedin.com" in u: return "linkedin"
    if "crunchbase.com" in u: return "crunchbase"
    if any(a in u for a in AGG): return "aggregator"
    if any(n in u for n in NEWS): return "news"
    if "youtube.com" in u or "twitter.com" in u or "x.com" in u: return "social"
    return "other"

def _ikey(sec, it):

    if not isinstance(it, dict):
        return re.sub(r"[^a-z0-9]", "", str(it).lower())[:60]
    base = (it.get("customer") or it.get("name") or it.get("text") or it.get("feature")
            or it.get("offering") or json.dumps(it, sort_keys=True))
    return re.sub(r"[^a-z0-9]", "", str(base).lower())[:60]

def count_items(sec, structured):

    if not isinstance(structured, dict):
        return 0, 0
    v = structured.get(SECTIONS[sec]["list_key"])
    if not isinstance(v, list):
        return 0, 0
    keys = [_ikey(sec, it) for it in v]
    keys = [k for k in keys if k]
    return len(v), len(set(keys))

def aggregate():
    raw, synth_d, judge_d = load_keys(RAW), load_keys(SYNTH), load_keys(JUDGE)
    eng = {e: {"qty": [], "raw_qty": [], "raw_tot": 0, "ded_tot": 0, "url_tot": 0, "url_fill": 0, "ent": [], "top": [], "right": 0, "n": 0, "src": defaultdict(int), "found_sections": defaultdict(set)} for e in ENGINES}
    itemsets = defaultdict(lambda: defaultdict(set))
    relC = defaultdict(lambda: defaultdict(list))
    for k, rec in synth_d.items():
        company, sec, engine = rec["company"], rec["section"], rec["engine"]
        if engine not in eng:
            continue
        raw_n, ded_n = count_items(sec, rec["structured"])
        eng[engine]["qty"].append(ded_n)
        eng[engine]["raw_qty"].append(raw_n)
        eng[engine]["raw_tot"] += raw_n; eng[engine]["ded_tot"] += ded_n
        if ded_n > 0:
            eng[engine]["found_sections"][sec].add(company)
        lst = rec["structured"].get(SECTIONS[sec]["list_key"]) if isinstance(rec["structured"], dict) else None
        if isinstance(lst, list):
            if sec in ("3_case_studies", "4_customers", "5_ctas"):
                for it in lst:
                    if isinstance(it, dict):
                        eng[engine]["url_tot"] += 1
                        if str(it.get("url", "")).startswith("http"): eng[engine]["url_fill"] += 1
            if sec in ("3_case_studies", "4_customers"):
                for it in lst:
                    kk = _ikey(sec, it)
                    if kk: itemsets[(company, sec)][engine].add(kk)

        for u in raw.get(k, {}).get("urls", []):
            eng[engine]["src"][classify(u, "")] += 1

    comp_dom = {}
    for c in load_companies():
        comp_dom[c["name"]] = c["domain"]
    for e in ENGINES:
        eng[e]["src"] = defaultdict(int)
    for k, rec in raw.items():
        engine = rec["engine"]
        if engine not in eng: continue
        dom = comp_dom.get(rec["company"], "")
        for u in rec.get("urls", []):
            eng[engine]["src"][classify(u, dom)] += 1

    for k, rec in judge_d.items():
        v = rec.get("verdict", {})
        for e in ENGINES:
            d = v.get(e)
            if isinstance(d, dict) and "entity_relevance" in d:
                eng[e]["ent"].append(d["entity_relevance"]); eng[e]["top"].append(d["topical_relevance"])
                eng[e]["right"] += int(d.get("right_company") is True); eng[e]["n"] += 1
                relC[rec["company"]][e].append((d["entity_relevance"] + d["topical_relevance"]) / 2)
    n_companies = len({rec["company"] for rec in synth_d.values()})
    def mean(x): return round(sum(x) / len(x), 1) if x else 0.0

    uniq = defaultdict(int); cov_e = defaultdict(int); cov_u = defaultdict(int)
    for (_co, _sec), emap in itemsets.items():
        union = set().union(*emap.values()) if emap else set()
        for e in ENGINES:
            mine = emap.get(e, set())
            others = set().union(*[emap[o] for o in emap if o != e]) if len(emap) > 1 else set()
            uniq[e] += len(mine - others); cov_e[e] += len(mine); cov_u[e] += len(union)

    def pctile(xs, pp):
        xs = sorted(xs); return round(xs[min(len(xs) - 1, int(pp * len(xs)))], 1) if xs else 0
    cons = {}
    for e in ENGINES:
        crel = [mean(relC[co][e]) for co in relC if relC[co].get(e)]
        cons[e] = {"p10": pctile(crel, 0.1), "bomb": round(100 * sum(1 for x in crel if x < 40) / len(crel)) if crel else 0}
    card = {"companies": n_companies, "engines": {}}
    for e in ENGINES:
        d = eng[e]
        comp_rate = {sec: round(100 * len(d["found_sections"].get(sec, set())) / max(1, n_companies)) for sec in SECTIONS}
        card["engines"][e] = {
            "items_per_company_deduped": round(d["ded_tot"] / max(1, n_companies), 1),
            "items_per_company_raw": round(d["raw_tot"] / max(1, n_companies), 1),
            "dup_rate_pct": round(100 * (d["raw_tot"] - d["ded_tot"]) / d["raw_tot"]) if d["raw_tot"] else 0,
            "entity_relevance": mean(d["ent"]),
            "topical_relevance": mean(d["top"]),
            "right_company_pct": round(100 * d["right"] / d["n"]) if d["n"] else 0,
            "completeness_pct_by_section": comp_rate,
            "url_backed_pct": round(100 * d["url_fill"] / d["url_tot"]) if d["url_tot"] else 0,
            "unique_finds": uniq[e],
            "union_coverage_pct": round(100 * cov_e[e] / cov_u[e]) if cov_u[e] else 0,
            "source_authority_pct": round(100 * (d["src"].get("own_site", 0) + d["src"].get("news", 0) + d["src"].get("crunchbase", 0)) / max(1, sum(d["src"].values()))),
            "aggregator_pct": round(100 * d["src"].get("aggregator", 0) / max(1, sum(d["src"].values()))),
            "p10_relevance": cons[e]["p10"],
            "bomb_rate_pct": cons[e]["bomb"],
            "source_mix": dict(sorted(d["src"].items(), key=lambda x: -x[1])),
        }

    tpath = os.path.join(OUT, "timings.jsonl")
    if os.path.exists(tpath):
        by = defaultdict(list)
        for l in open(tpath):
            try:
                o = json.loads(l); by[o["label"]].append(o["ms"])
            except Exception:
                pass
        def pct(xs, p):
            xs = sorted(xs); return round(xs[min(len(xs) - 1, int(p * len(xs)))], 0) if xs else 0
        lat = {}
        for lab, xs in by.items():
            lat[lab] = {"n": len(xs), "median_ms": round(mean(xs)), "p50_ms": pct(xs, 0.5),
                        "p95_ms": pct(xs, 0.95), "max_ms": round(max(xs)) if xs else 0}
        card["latency_ms"] = lat
        print("\n=== LATENCY (per HTTP call, ms) ===")
        print(f"{'stage':22}{'n':>7}{'p50':>8}{'p95':>8}{'max':>8}")
        for lab in sorted(lat):
            d = lat[lab]; print(f"{lab:22}{d['n']:>7}{d['p50_ms']:>8.0f}{d['p95_ms']:>8.0f}{d['max_ms']:>8.0f}")
    json.dump(card, open(SCORECARD, "w"), indent=2)
    print(f"\nSAVED {SCORECARD}")

def dry_run(companies):
    print(f"=== DRY RUN — no API calls ===\n")
    print(f"DB: {DB}")
    print(f"companies loaded: {len(companies)}  | sections: {len(SECTIONS)}  | engines: {len(ENGINES)}")
    units = len(companies) * len(SECTIONS) * len(ENGINES)
    print(f"PLAN: {units} retrieval+synth units  +  {len(companies)*len(SECTIONS)} judge calls\n")
    keyspresent = [e for e in ENGINES if KEYS[e]] + (["anthropic"] if ANTHROPIC_KEY else [])
    print(f"keys present: {', '.join(keyspresent)}\n")
    c = companies[0]
    print("─" * 70)
    print(f"SAMPLE — first company: {c['name']}\n")
    print(disambig_block(c))
    for sec in SECTIONS:
        print(f"\n[{sec}] searches:")
        for q in render_searches(sec, c):
            print(f"   • {q}")
        print(f"   scrape: {SECTIONS[sec]['scrape'] and not SEARCH_ONLY}  -> {c['url']}")
    print("\n─" * 1)
    print("SYNTH system prompt (offering example):")
    print(SYNTH_SYS.format(task=SECTIONS['1_offering']['synth'], schema=json.dumps(SECTIONS['1_offering']['schema']))[:700], "...")
    print("\nJUDGE system prompt:\n", JUDGE_SYS[:500], "...")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--aggregate", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--concurrency", type=int, default=24,
                    help="max (company,section) groups in flight; throttle is the per-provider QPS limiters")
    ap.add_argument("--search-only", action="store_true",
                    help="one search endpoint per engine, no page scrape/extract; Exa returns highlights (excerpts). "
                         "Stores in results_search_only/")
    ap.add_argument("--companies", default=None,
                    help="dataset path (.json or .csv); default data/companies_150.csv. Use data/companies_100.json for the search-only bench")
    a = ap.parse_args()
    global SEARCH_ONLY, DB, OUT, RAW, SYNTH, JUDGE, SCORECARD
    if a.companies:
        DB = a.companies if os.path.isabs(a.companies) else os.path.join(HERE, a.companies)
    if a.search_only:
        SEARCH_ONLY = True
        OUT = os.path.join(HERE, "results_search_only")
        RAW, SYNTH, JUDGE = (os.path.join(OUT, f) for f in ("raw.jsonl", "synth.jsonl", "judge.jsonl"))
        SCORECARD = os.path.join(OUT, "scorecard.json")
    if a.aggregate:
        aggregate(); return
    companies = load_companies(a.limit, a.offset)
    if not companies:
        sys.exit("no companies loaded (check DB path / columns)")
    if a.dry_run:
        dry_run(companies); return
    missing = [e for e in ENGINES if not KEYS[e]] + ([] if ANTHROPIC_KEY else ["ANTHROPIC"])
    if missing:
        sys.exit(f"missing keys: {missing}")
    os.makedirs(OUT, exist_ok=True)
    print(f"running {len(companies)} companies × {len(SECTIONS)} sections × {len(ENGINES)} engines "
          f"@ concurrency {a.concurrency}\n")
    asyncio.run(run(companies, a.concurrency))

if __name__ == "__main__":
    main()
