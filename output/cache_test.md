# Problem 4 — With and without cached tokens

All 12 practice documents, run twice: once with prompt caching working, once
with it defeated. 24 model runs (48 HTTP requests) logged in
[`output/cache_test.json`](cache_test.json).

Model **gpt-6-luna** · prices from `data/prices.json`
(input $0.10 / cached input $0.01 / output $0.50 per 1M tokens).

## How the two setups were built

The handbook is appended to the system prompt, so it is sent on every call in
both setups — **the two setups do identical work**. The only difference is
whether the prefix can be reused.

| Setup | How |
|---|---|
| **with_cache** | A byte-identical system prompt on every request, so the provider serves the handbook prefix from its cache. |
| **without_cache** | A fresh `<!-- cache-buster <uuid> -->` line is prepended to the prompt. Because it changes byte 0, the whole prefix misses. It is registered as a pydantic-ai `@agent.instructions` function, which is re-evaluated on **every request**, not just every run. |

### Proof that both setups work

The API's own `cached_input_tokens` confirms it:

| Setup | Input tokens | Cached input tokens | Cache hit rate |
|---|---|---|---|
| with_cache | 270,559 | **254,016** | **93.9 %** |
| without_cache | 271,255 | **0** | **0.0 %** |

The without-cache setup shows **exactly zero** cached tokens on all 12 runs, so
nothing was reused. This took a second attempt — see "Surprises" below.

---

## a) Total cost, cost per document, and savings

| Setup | Input | Cached | Output | Total cost | Cost per document |
|---|---|---|---|---|---|
| **with_cache** | 270,559 | 254,016 | 1,382 | **$0.004885** | **$0.000407** |
| **without_cache** | 271,255 | 0 | 1,346 | **$0.027799** | **$0.002317** |

```
saved = $0.027799 − $0.004885 = $0.022913
      = 82.43 % cheaper
```

**Caching cut the cost of the 12-document batch by 82.4 %.**

That 82.4 % is dragged down by one cold call. The very first with-cache run
(p01) had to *write* the cache and cost $0.001324 — 4× a warm call. Excluding
it, the steady-state cost is **$0.000324 per document**, which is
**86.0 % cheaper** than the uncached $0.002317.

All 24 runs produced the same decision for the same document, so caching
changed cost only, never the answer. (7 `do_not_recommend`, 5 `recommend`.)

---

## b) Comparison with the Problem 2 estimates

| | Problem 2 estimate | Problem 4 actual | Difference |
|---|---|---|---|
| Tokens charged per call | 10,058 (handbook only) | ~22,550 input | **2.24× higher** |
| Uncached cost, 1 call | $0.0010058 | $0.002317 | **2.30× higher** |
| Uncached cost, 1,000 calls | $1.0058 | $2.3166 | **2.30× higher** |
| Cached cost, 1,000 calls | $0.1017 | $0.3240 | **3.19× higher** |
| Cache saving | ~90 % | 86.0 % | 4 points worse |

**The Problem 2 estimate was about 2.3× too low.** It was not wrong — it
measured exactly what it claimed, the handbook alone — but a real call carries
much more than the handbook:

| Component | ~Tokens |
|---|---|
| Handbook | 10,058 |
| Agent instructions (`prompts/prompt.md`) | ~700 |
| Tool schemas (3 tools) + output schema | ~500 |
| User message + chat wrapper | ~50 |
| **Subtotal, one request** | **~11,300** |
| **× 2 requests** (the tool-calling loop: ask → tool result → answer) | **~22,550** |

The single biggest factor is one Problem 2 did not model at all: **the agent
sends the handbook twice per document**, once to decide to call
`read_document` and again with the tool result. That doubling alone accounts
for most of the 2.3× gap.

The cache saving also came in slightly below the predicted 90 %, because the
~1,300 tokens at the end of request 2 (the tool result and the document text)
are different every time and can never be cached, and output tokens are billed
at the full $0.50/1M regardless.

**Lesson:** estimate from the whole request, not from the biggest document in
it, and multiply by the number of model round-trips the agent actually makes.

---

## c) Projection: 1,000 documents a day for 30 days

30,000 documents. Using the measured per-document costs:

| Setup | Per document | Per day | **Per 30 days** |
|---|---|---|---|
| **without_cache** | $0.002317 | $2.32 | **$69.50** |
| **with_cache** (steady state) | $0.000324 | $0.32 | **$9.71** |
| **Savings** | $0.001993 | $1.99 | **$59.78 (86.0 %)** |

```
without:  $0.002317 × 1,000 × 30 = $69.50
with:     $0.000324 × 1,000 × 30 = $ 9.71
saved:                             $59.78
```

For comparison, the Problem 2 estimate would have predicted $30.17 uncached and
$3.05 cached — understating the real bill by about $39 a month.

At 1,000 documents a day the cache writes are negligible: the prefix is rewritten
only when it expires, and at that volume a warm cache is hit essentially
continuously. The saving is real money but modest in absolute terms — $60/month —
because gpt-6-luna is cheap. On a model priced like a frontier model (~30× more),
the same workload and the same 86 % saving would be ~$1,800/month saved.

---

## d) Surprises

**1. The first "without cache" attempt still showed ~11,000 cached tokens.**
The nonce was generated once per *run*, so the run's two requests shared a
prefix: request 1 wrote the cache and request 2 hit it. The setup was measuring
"cache across documents off, cache within a document on" — not a true control.
Fixed by moving the nonce into an `@agent.instructions` function, which
pydantic-ai re-evaluates per request. Cached tokens then dropped to exactly 0.
**This is the real lesson of the problem:** an agent caches *within* a single
run too, and if you only disable caching between runs you will under-report the
true cost of running uncached by about half.

**2. The cold cache write cost 4× a warm call.** p01 with caching "on" cost
$0.001324 against $0.000324 for p02–p12. Caching is not free on the first call,
and a low-volume workload where the cache always expires between documents can
end up *more* expensive than not caching at all.

**3. The cache hit rate topped out at 93.9 %, not 100 %.** The last ~460 tokens
of request 2 — the vendor document text and tool-result wrapper — are different
for every document and sit *after* the cached prefix, so they can never be
reused. This is why putting the handbook first and the document last matters: a
prompt that interleaved them would cache almost nothing.

**4. Input tokens were slightly *higher* without caching** (271,255 vs 270,559),
even though the work was identical. That is the cache-buster comment itself —
~25 extra tokens per request, ~58 per run. Measuring the cost of not caching
costs a little extra.

**5. Caching never changed an answer.** All 12 documents produced identical
decisions in both setups. Worth confirming rather than assuming: the cache
returns the same tokens, not a cheaper approximation of them.
