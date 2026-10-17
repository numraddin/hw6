"""Count tokens in the Campus Customs Shop Handbook and estimate its cost.

Run:  .venv/bin/python scripts/count_handbook_tokens.py
"""
import json
import pathlib

import tiktoken

ROOT = pathlib.Path(__file__).resolve().parent.parent
HANDBOOK = ROOT / "data" / "shop_handbook.md"
PRICES = ROOT / "data" / "prices.json"
MODEL = "gpt-6-luna"

text = HANDBOOK.read_text(encoding="utf-8")
# gpt-6-luna is not a tiktoken-registered model, so we use o200k_base,
# the encoding used by the current GPT-4o / GPT-5 family.
enc = tiktoken.get_encoding("o200k_base")
tokens = len(enc.encode(text))

prices = json.loads(PRICES.read_text(encoding="utf-8"))[MODEL]

print(f"characters : {len(text):,}")
print(f"words      : {len(text.split()):,}")
print(f"tokens     : {tokens:,}  (o200k_base)")
print(f"chars/token: {len(text)/tokens:.2f}")
print()

m = tokens / 1_000_000
uncached_1 = m * prices["input_per_1m"]
cached_1 = m * prices["cached_input_per_1m"]
cache_write = m * prices["cache_write_per_1m"]

print(f"1 call, uncached        : ${uncached_1:.6f}")
print(f"1 call, cached read     : ${cached_1:.6f}")
print(f"1 cache write           : ${cache_write:.6f}")
print(f"1,000 calls, uncached   : ${uncached_1*1000:.4f}")
print(f"1,000 calls, all cached : ${cached_1*1000:.4f}")
print(f"1,000 calls, 1 write +   999 cached reads: "
      f"${cache_write + cached_1*999:.4f}")
