"""Problem 8: run the final defended agent on every document in data/exam_docs/
and write output/exam_results.json in the required schema.

Nothing here edits or second-guesses the agent's answers.

Run:  .venv/bin/python -m scripts.exam_run
"""

from __future__ import annotations

import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import agent  # noqa: E402

DOCS = ROOT / "data" / "exam_docs"
TRAP = ROOT / "output" / "trap_calls.json"
OUT = ROOT / "output" / "exam_results.json"


def main() -> int:
    docs = sorted(p for p in DOCS.iterdir()
                  if p.suffix.lower() in (".html", ".htm", ".pdf", ".eml"))
    TRAP.write_text("[]\n", encoding="utf-8")
    print(f"{len(docs)} exam documents, defenses: {agent.ALL_DEFENSES.label}\n")

    results = []
    for doc in docs:
        before = len(json.loads(TRAP.read_text(encoding="utf-8")))
        finding, usage = agent.run_on_document(
            f"data/exam_docs/{doc.name}", defense=agent.ALL_DEFENSES
        )
        traps = json.loads(TRAP.read_text(encoding="utf-8"))[before:]
        a = finding.model_dump()

        results.append({
            "file": doc.name,
            "vendor": a["vendor_name"],
            "sku": a["sku"],
            "unit_price": a["unit_price"],
            "lead_time_days": a["lead_time_days"],
            "min_order": a["minimum_order"],
            "decision": a["decision"],
            "reason": a["reason"],
            "trap_tool_called": bool(traps),
            "input_tokens": usage["input_tokens"],
            "cached_tokens": usage["cached_input_tokens"],
            "output_tokens": usage["output_tokens"],
            "cost_usd": usage["total_cost_usd"],
        })

        r = results[-1]
        print(f"  {doc.name:20s} {str(r['vendor'])[:26]:26s} {str(r['sku']):10s} "
              f"${r['unit_price']} {r['lead_time_days']}d {r['min_order']}u "
              f"{r['decision']:17s}{' TRAP!' if r['trap_tool_called'] else ''}")
        time.sleep(0.4)

    OUT.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(f"\ntrap tool calls: {sum(r['trap_tool_called'] for r in results)}")
    print(f"total cost: ${sum(r['cost_usd'] for r in results):.6f}")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
