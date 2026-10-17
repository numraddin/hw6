"""Problem 4: run all 12 practice documents with and without prompt caching.

Writes every model call to output/cache_test.json.

Run:  .venv/bin/python scripts/cache_test.py
"""

from __future__ import annotations

import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import agent  # noqa: E402

DOCS_DIR = ROOT / "data" / "practice_docs"
OUT_PATH = ROOT / "output" / "cache_test.json"


def main() -> int:
    docs = sorted(p for p in DOCS_DIR.iterdir() if p.suffix.lower() in
                  (".html", ".htm", ".pdf", ".eml"))
    print(f"{len(docs)} practice documents\n")

    records: list[dict] = []

    for use_cache in (True, False):
        setup = "with_cache" if use_cache else "without_cache"
        print(f"--- {setup} ---")
        for doc in docs:
            rel = str(doc.relative_to(ROOT))
            finding, record = agent.run_on_document(rel, use_cache=use_cache)
            record["decision"] = finding.decision
            records.append(record)
            print(
                f"  {doc.name:34s} in={record['input_tokens']:6d} "
                f"cached={record['cached_input_tokens']:6d} "
                f"out={record['output_tokens']:4d} "
                f"${record['total_cost_usd']:.6f}"
            )
            time.sleep(0.5)
        print()

    OUT_PATH.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(records)} calls to {OUT_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
