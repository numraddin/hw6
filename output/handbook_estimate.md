# Problem 2 — Size up the handbook

Model: **gpt-6-luna** · Prices from `data/prices.json` (per 1M tokens)

| Price type | $ / 1M tokens |
|---|---|
| Input (uncached) | $0.10 |
| Cached input (read) | $0.01 |
| Cache write | $0.125 |
| Output | $0.50 |

---

## a) Total number of tokens

**`data/shop_handbook.md` = 10,058 tokens**

### How it was calculated

I tokenized the file with OpenAI's `tiktoken` library rather than guessing from
word count, so the number is an exact token count and not a ratio estimate.

Script: [`scripts/count_handbook_tokens.py`](../scripts/count_handbook_tokens.py)

```python
import tiktoken
text = open("data/shop_handbook.md", encoding="utf-8").read()
enc  = tiktoken.get_encoding("o200k_base")
tokens = len(enc.encode(text))   # -> 10058
```

`gpt-6-luna` is not a model name registered inside `tiktoken`, so I used
**`o200k_base`**, the encoding used by the current GPT-4o / GPT-5 generation —
the closest available stand-in for a GPT-6-class tokenizer.

Sanity check on the raw file size:

| Measure | Value |
|---|---|
| Characters | 28,903 |
| Words | 6,127 |
| Tokens (o200k_base) | **10,058** |
| Characters per token | 2.87 |
| Tokens per word | 1.64 |

2.87 characters/token is in the expected range for English Markdown (the
rule-of-thumb is ~4 chars/token for prose; Markdown runs denser because
`#`, `-`, `**`, `|` and newlines each cost their own token).

> Note: this is the handbook **alone**. A real call also carries the system
> prompt wrapper, the vendor document, and the output tokens — so the live
> numbers in Problem 4 should come out *above* these figures.

---

## b) Cost of the handbook per call

Let **T = 10,058 tokens = 0.010058 M tokens**.

The general formula is:

```
cost = (tokens / 1,000,000) × price_per_1M
```

### One call

| Scenario | Calculation | Cost |
|---|---|---|
| **Uncached** (full price input) | 0.010058 M × $0.10 | **$0.0010058** ≈ 0.1¢ |
| **Cached read** (handbook already in cache) | 0.010058 M × $0.01 | **$0.0001006** ≈ 0.01¢ |
| *Cache write* (one-time, to put it in cache) | 0.010058 M × $0.125 | *$0.0012573* |

### 1,000 calls

| Scenario | Calculation | Cost |
|---|---|---|
| **Uncached — every call pays full input price** | $0.0010058 × 1,000 | **$1.0058** |
| **Cached — every call reads from cache** | $0.0001006 × 1,000 | **$0.1006** |
| **Realistic cached run** — 1 cache write + 999 cached reads | $0.0012573 + ($0.0001006 × 999) = $0.0012573 + $0.1005 | **$0.1017** |

### Savings

```
$1.0058 − $0.1017 = $0.9041 saved
$0.9041 / $1.0058 = 89.9% cheaper
```

**Caching the handbook cuts its cost by ~90%** (the cached read price is 1/10th
of the input price, and the single $0.00126 cache write is negligible across
1,000 calls).

One caveat: the cache write costs **1.25×** a normal input token, so caching only
pays off if the handbook is reused. Break-even is after about **2 calls** —
beyond that every call saves 0.09¢.

---

*These estimates will be compared with actual measured usage in Problem 4.*
