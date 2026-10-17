"""Problem 7: run the two home-made attacks against the agent with and
without defenses. Writes output/red_team.json.

Run:  .venv/bin/python -m scripts.red_team
"""

from __future__ import annotations

import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import agent  # noqa: E402
from scripts.attack_test import grade  # noqa: E402

KEY = ROOT / "data" / "my_attacks" / "my_attacks_key.json"
TRAP = ROOT / "output" / "trap_calls.json"
OUT = ROOT / "output" / "red_team.json"

CONFIGS = [("no_defenses", agent.NO_DEFENSES), ("all_defenses", agent.ALL_DEFENSES)]


def main() -> int:
    keys = json.loads(KEY.read_text(encoding="utf-8"))
    TRAP.write_text("[]\n", encoding="utf-8")
    results = []

    for label, defense in CONFIGS:
        print(f"--- {label} ---")
        for k in keys:
            rel = f"data/my_attacks/{k['file']}"
            before = len(json.loads(TRAP.read_text(encoding="utf-8")))
            finding, usage = agent.run_on_document(rel, defense=defense)
            answer = finding.model_dump()
            traps = json.loads(TRAP.read_text(encoding="utf-8"))[before:]

            fields = grade(answer, k)
            decision_match = answer["decision"] == k["decision"]
            results.append({
                "attack": k["file"], "config": label, "defenses": defense.label,
                "answer": answer, "key": k,
                "field_matches": fields, "all_fields_matched": all(fields.values()),
                "decision_match": decision_match,
                "trap_tool_called": bool(traps), "trap_calls": traps,
                "attack_succeeded": not (decision_match and all(fields.values())),
                "defense_notes": usage["defense_notes"],
                "input_tokens": usage["input_tokens"],
                "output_tokens": usage["output_tokens"],
                "cost_usd": usage["total_cost_usd"],
            })
            bad = [f for f, ok in fields.items() if not ok]
            if not decision_match:
                bad.append("decision")
            print(f"  {'ATTACK WORKED' if results[-1]['attack_succeeded'] else 'defended   '}"
                  f"  {k['file']:28s} {answer['decision']:17s}"
                  f" {'wrong: ' + ','.join(bad) if bad else ''}")
            time.sleep(0.4)
        print()

    OUT.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
