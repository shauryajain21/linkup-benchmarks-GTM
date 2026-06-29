import argparse
import csv
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

DOTENV = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")

def _merge(base, params):
    out = dict(base)
    out.update(params or {})
    return out

def _linkup_search_body(q, p):
    return _merge({"q": q, "depth": "standard", "outputType": "sourcedAnswer"}, p)

def _linkup_search_extract(r):
    if isinstance(r, dict):
        if "answer" in r:
            return r["answer"]
        if "results" in r:
            return json.dumps(r["results"], ensure_ascii=False)
        if "data" in r:
            return json.dumps(r["data"], ensure_ascii=False)
    return json.dumps(r, ensure_ascii=False)

def _linkup_fetch_body(q, p):
    return _merge({"url": q}, p)

def _linkup_fetch_extract(r):
    if isinstance(r, dict) and "markdown" in r:
        return r["markdown"]
    return json.dumps(r, ensure_ascii=False)

def _exa_answer_body(q, p):
    return _merge({"query": q, "text": True}, p)

def _exa_answer_extract(r):
    if isinstance(r, dict) and r.get("answer") is not None:
        a = r["answer"]
        return a if isinstance(a, str) else json.dumps(a, ensure_ascii=False)
    return json.dumps(r, ensure_ascii=False)

def _exa_search_body(q, p):
    return _merge({"query": q, "type": "auto", "numResults": 10}, p)

def _exa_results_extract(r):
    if isinstance(r, dict) and "results" in r:
        return json.dumps(r["results"], ensure_ascii=False)
    return json.dumps(r, ensure_ascii=False)

def _exa_contents_body(q, p):
    return _merge({"urls": [q], "text": True}, p)

def _ppx_body(q, p):
    p = p or {}
    body = {"model": p.get("model", "sonar"),
            "messages": [{"role": "user", "content": q}]}
    for k, v in p.items():
        if k != "model":
            body[k] = v
    return body

def _ppx_extract(r):
    try:
        return r["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return json.dumps(r, ensure_ascii=False)

def _ppx_search_body(q, p):
    return _merge({"query": q, "max_results": 10}, p)

def _ppx_search_extract(r):
    if isinstance(r, dict) and "results" in r:
        return json.dumps(r["results"], ensure_ascii=False)
    return json.dumps(r, ensure_ascii=False)

def _parallel_search_body(q, p):
    return _merge({"objective": q, "search_queries": [q], "mode": "advanced"}, p)

def _parallel_search_extract(r):
    if isinstance(r, dict) and "results" in r:
        lines = []
        for it in r["results"]:
            title, url = it.get("title") or "", it.get("url") or ""
            ex = " ".join(it.get("excerpts", []) or [])
            lines.append(f"[{title}]({url}) {ex}".strip())
        return "\n".join(lines)
    return json.dumps(r, ensure_ascii=False)

def _parallel_task_body(q, p):
    return _merge({"input": q, "processor": "base"}, p)

def _parallel_task_extract(r):
    out = r.get("output", {}) if isinstance(r, dict) else {}
    c = out.get("content")
    if c is None:
        return json.dumps(r, ensure_ascii=False)
    return c if isinstance(c, str) else json.dumps(c, ensure_ascii=False)

def _inj_linkup(body, schema):
    body["outputType"] = "structured"
    body["structuredOutputSchema"] = json.dumps(schema)
    return body

def _xs_linkup(r):
    if isinstance(r, dict) and "data" in r and "sources" in r:
        r = r["data"]
    return r if isinstance(r, str) else json.dumps(r, ensure_ascii=False)

def _inj_exa(body, schema):
    body["outputSchema"] = schema
    return body

def _xs_exa(r):
    out = r.get("output") if isinstance(r, dict) else None
    if isinstance(out, dict) and "content" in out:
        out = out["content"]
    if out is None:
        out = r
    return out if isinstance(out, str) else json.dumps(out, ensure_ascii=False)

def _inj_ppx(body, schema):
    body["response_format"] = {"type": "json_schema", "json_schema": {"schema": schema}}
    return body

def _inj_parallel_task(body, schema):
    body["task_spec"] = {"output_schema": {"type": "json", "json_schema": schema}}
    return body

def _xs_parallel_task(r):
    out = r.get("output", {}) if isinstance(r, dict) else {}
    c = out.get("content")
    if c is None:
        return json.dumps(r, ensure_ascii=False)
    return c if isinstance(c, str) else json.dumps(c, ensure_ascii=False)

PROVIDERS = {
    "linkup": {
        "env": "LINKUP_API_KEY",
        "auth": lambda k: {"Authorization": f"Bearer {k}"},
        "qps": 25,
        "default_endpoint": "search",
        "endpoints": {
            "search": {"kind": "post", "url": "https://api.linkup.so/v1/search",
                       "build": _linkup_search_body, "extract": _linkup_search_extract,
                       "inject": _inj_linkup, "xstract": _xs_linkup,
                       "outputs": "outputType: sourcedAnswer | searchResults | structured; depth: fast | standard | deep"},
            "fetch":  {"kind": "post", "url": "https://api.linkup.so/v1/fetch",
                       "build": _linkup_fetch_body, "extract": _linkup_fetch_extract,
                       "outputs": "markdown (query = URL); renderJs, includeRawHtml, extractImages"},
        },
    },
    "exa": {
        "env": "EXA_API_KEY",
        "auth": lambda k: {"x-api-key": k},
        "qps": 10,
        "default_endpoint": "answer",
        "endpoints": {
            "answer":   {"kind": "post", "url": "https://api.exa.ai/answer",
                         "build": _exa_answer_body, "extract": _exa_answer_extract,
                         "inject": _inj_exa, "xstract": _xs_exa,
                         "outputs": "synthesized answer + citations; text(bool), outputSchema(object)"},
            "search":   {"kind": "post", "url": "https://api.exa.ai/search",
                         "build": _exa_search_body, "extract": _exa_results_extract,
                         "inject": _inj_exa, "xstract": _xs_exa,
                         "outputs": "ranked results; type: instant|fast|auto|deep-lite|deep|deep-reasoning, numResults, category, contents{...}, outputSchema"},
            "contents": {"kind": "post", "url": "https://api.exa.ai/contents",
                         "build": _exa_contents_body, "extract": _exa_results_extract,
                         "outputs": "page text/highlights/summary (query = URL); text, highlights, summary, livecrawl"},
        },
    },
    "perplexity": {
        "env": "PERPLEXITY_API_KEY",
        "auth": lambda k: {"Authorization": f"Bearer {k}"},
        "qps": 10,
        "default_endpoint": "chat",
        "endpoints": {
            "chat": {"kind": "post", "url": "https://api.perplexity.ai/chat/completions",
                     "build": _ppx_body, "extract": _ppx_extract,
                     "inject": _inj_ppx, "xstract": _ppx_extract,
                     "outputs": "model: sonar | sonar-pro | sonar-reasoning | sonar-reasoning-pro | sonar-deep-research; response_format, search_* filters, web_search_options"},
            "search": {"kind": "post", "url": "https://api.perplexity.ai/search",
                       "build": _ppx_search_body, "extract": _ppx_search_extract,
                       "outputs": "raw web results (Search API); query, max_results, max_tokens_per_page"},
        },
    },
    "parallel": {
        "env": "PARALLEL_API_KEY",
        "auth": lambda k: {"x-api-key": k},
        "qps": 10,
        "default_endpoint": "search",
        "endpoints": {
            "search": {"kind": "post", "url": "https://api.parallel.ai/v1/search",
                       "build": _parallel_search_body, "extract": _parallel_search_extract,
                       "outputs": "ranked excerpts (no synthesized answer); mode: basic | advanced, advanced_settings{max_results, source_policy, ...}"},
            "task":   {"kind": "task_poll", "url": "https://api.parallel.ai/v1/tasks/runs",
                       "build": _parallel_task_body, "extract": _parallel_task_extract,
                       "inject": _inj_parallel_task, "xstract": _xs_parallel_task,
                       "outputs": "async structured + citations; processor: lite | base | core | pro | ultra (append -fast), task_spec{output_schema}"},
        },
    },
}

def load_dotenv():
    if not os.path.exists(DOTENV):
        return
    with open(DOTENV) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            os.environ.setdefault(k, v)

class RateLimiter:

    def __init__(self, qps):
        self.interval = 1.0 / float(qps) if qps > 0 else 0.0
        self.lock = threading.Lock()
        self.next_slot = 0.0

    def acquire(self):
        with self.lock:
            now = time.monotonic()
            if self.next_slot - now > 0:
                time.sleep(self.next_slot - now)
                now = time.monotonic()
            self.next_slot = max(now, self.next_slot) + self.interval

def _request(method, url, headers, body, timeout):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    hdrs = {"Content-Type": "application/json"}
    hdrs.update(headers)
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))

def run_one(cfg, ep, headers, query, params, limiter, timeout, max_wait, schema=None):
    body = ep["build"](query, params)
    if schema is not None and ep.get("inject"):
        body = ep["inject"](body, schema)
    extract = ep["xstract"] if (schema is not None and ep.get("xstract")) else ep["extract"]
    params_json = json.dumps(body, ensure_ascii=False, sort_keys=True)
    limiter.acquire()
    t0 = time.monotonic()
    try:
        if ep["kind"] == "task_poll":
            created = _request("POST", ep["url"], headers, body, timeout)
            run_id = created["run_id"]
            result_url = f"{ep['url']}/{run_id}/result"
            deadline = time.monotonic() + max_wait
            resp = None
            while time.monotonic() < deadline:
                try:
                    poll_to = min(60, max(5, int(deadline - time.monotonic())))
                    resp = _request("GET", f"{result_url}?timeout={poll_to}",
                                    headers, None, poll_to + 15)
                    break
                except urllib.error.HTTPError as e:
                    if e.code == 408:
                        continue
                    raise
            if resp is None:
                raise TimeoutError(f"task {run_id} not done within {max_wait}s")
            text, err = extract(resp), ""
        else:
            resp = _request("POST", ep["url"], headers, body, timeout)
            text, err = extract(resp), ""
    except urllib.error.HTTPError as e:
        text = f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:500]}"
        err = "http_error"
    except Exception as e:
        text = f"ERROR: {type(e).__name__}: {e}"
        err = "error"
    return {"query": query, "response": text, "params": params_json,
            "_latency": round(time.monotonic() - t0, 3), "_err": err}

def load_queries(args):
    if args.queries_json:
        with open(args.queries_json) as f:
            items = json.load(f)
        out = []
        for it in items:
            out.append((it, {}) if isinstance(it, str) else (it["query"], it.get("params", {})))
        return out
    base = json.loads(args.params) if args.params else {}
    with open(args.queries) as f:
        return [(ln.strip(), dict(base)) for ln in f if ln.strip()]

def print_list():
    print("Providers / endpoints / output types & key params:\n")
    for name, cfg in PROVIDERS.items():
        print(f"  {name}  (env {cfg['env']}, {cfg['qps']} QPS, default endpoint: {cfg['default_endpoint']})")
        for ep_name, ep in cfg["endpoints"].items():
            print(f"    --endpoint {ep_name:9s} [{ep['kind']}]  {ep['url']}")
            print(f"        {ep['outputs']}")
        print()

def main():
    ap = argparse.ArgumentParser(description="Parallel single-provider/-endpoint search runner.")
    ap.add_argument("--provider", choices=list(PROVIDERS))
    ap.add_argument("--endpoint", help="endpoint/output mode (see --list); defaults to provider default")
    ap.add_argument("--queries", help="file with one query (or URL) per line")
    ap.add_argument("--queries-json", help="JSON list of strings or {query,params}")
    ap.add_argument("--params", help="JSON object merged into every request body (tweak ANY param)")
    ap.add_argument("--schema", help="path to a JSON Schema file; injected as each engine's structured-output param")
    ap.add_argument("--qps", type=float, help="override provider default QPS")
    ap.add_argument("--out", default="results", help="output directory (default: results/)")
    ap.add_argument("--timeout", type=float, default=120.0, help="per-request timeout (s)")
    ap.add_argument("--max-wait", type=float, default=900.0, help="async task overall budget (s)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the exact request bodies that WOULD be sent, then exit (confirm output type first)")
    ap.add_argument("--list", action="store_true", help="list providers/endpoints/output types and exit")
    args = ap.parse_args()

    load_dotenv()

    if args.list:
        print_list()
        return
    if not args.provider:
        ap.error("--provider is required (or use --list)")
    if not args.queries and not args.queries_json:
        ap.error("provide --queries or --queries-json (or --list)")

    cfg = PROVIDERS[args.provider]
    ep_name = args.endpoint or cfg["default_endpoint"]
    if ep_name not in cfg["endpoints"]:
        ap.error(f"{args.provider} has no endpoint '{ep_name}'. Options: {list(cfg['endpoints'])}")
    ep = cfg["endpoints"][ep_name]
    schema = None
    if args.schema:
        with open(args.schema) as f:
            schema = json.load(f)
        if not ep.get("inject"):
            ap.error(f"{args.provider}/{ep_name} does not support structured output (--schema).")
    items = load_queries(args)
    if not items:
        sys.exit("No queries to run.")

    def _preview_body(q, p):
        b = ep["build"](q, p)
        return ep["inject"](b, schema) if (schema is not None and ep.get("inject")) else b

    if args.dry_run:
        print(f"DRY RUN — {args.provider}/{ep_name} ({ep['kind']}) -> {ep['url']}", file=sys.stderr)
        print(f"Output type / tweakable params: {ep['outputs']}", file=sys.stderr)
        if schema is not None:
            print("Structured output: schema injected.", file=sys.stderr)
        for q, p in items[:50]:
            print(json.dumps(_preview_body(q, p), ensure_ascii=False, sort_keys=True))
        if len(items) > 50:
            print(f"... (+{len(items)-50} more)", file=sys.stderr)
        print(f"\n{len(items)} requests would be sent. Re-run without --dry-run to execute.", file=sys.stderr)
        return

    key = os.environ.get(cfg["env"])
    if not key:
        sys.exit(f"Missing API key: set {cfg['env']} in the environment or {DOTENV}.")
    headers = cfg["auth"](key)
    qps = args.qps if args.qps else cfg["qps"]
    limiter = RateLimiter(qps)

    os.makedirs(args.out, exist_ok=True)
    out_path = os.path.join(args.out, f"{args.provider}.csv")
    workers = max(1, min(int(qps * 2) or 1, len(items), 64))
    rows = []
    print(f"[{args.provider}/{ep_name}] {len(items)} queries @ {qps} QPS, {workers} workers", file=sys.stderr)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(run_one, cfg, ep, headers, q, p, limiter, args.timeout, args.max_wait, schema)
                for q, p in items]
        for fut in as_completed(futs):
            r = fut.result()
            rows.append(r)
            print(f"[{args.provider}/{ep_name}] done {r['query'][:50]!r} ({r['_err'] or str(r['_latency'])+'s'})",
                  file=sys.stderr)

    rows.sort(key=lambda r: r["query"])
    with open(out_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["provider", "endpoint", "query", "response", "params"])
        for r in rows:
            w.writerow([args.provider, ep_name, r["query"], r["response"], r["params"]])
    n_err = sum(1 for r in rows if r["_err"])
    print(f"[{args.provider}/{ep_name}] wrote {len(rows)} rows -> {out_path} ({n_err} errors)", file=sys.stderr)

if __name__ == "__main__":
    main()
