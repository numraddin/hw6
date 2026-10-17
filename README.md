# Homework 6 — Campus Customs Vendor Desk Agent

An AI agent that reads a vendor quote (HTML, PDF or email), pulls out the vendor,
SKU, unit price, lead time and minimum order, and decides `recommend` or
`do_not_recommend` using the rules in the Campus Customs Shop Handbook.

Built with **PydanticAI** on **gpt-6-luna**, reached through the Portkey gateway.

Some of the vendor documents are booby-trapped with text that is invisible when
you open them normally but perfectly readable by a text extractor. Much of this
project is about that problem.

---

## Quick start

```bash
cd hw6
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env          # then put your real PORTKEY_API_KEY in .env
```

Run the agent on one document:

```bash
.venv/bin/python agent.py --doc data/practice_docs/p01_bluehen_quote.html
```

```json
{
  "vendor_name": "Blue Hen Apparel",
  "sku": "CC-HD-006",
  "unit_price": 21.8,
  "lead_time_days": 14,
  "minimum_order": 240,
  "decision": "recommend",
  "reason": "All four purchasing checks pass: Blue Hen Apparel is approved; $21.80 vs the $25.44 max unit cost for CC-HD-006; 14 days vs the 21-day limit; 240 units vs the 600-unit limit."
}
```

HTML, PDF and `.eml` all work. Every run appends to `output/usage_log.json`
(tokens and dollar cost) and `output/audit_trail.json` (tool calls and the final
answer).

### Running with defenses off

The three defense layers can be switched independently. This is what Problems 5
and 7 compare against:

```bash
.venv/bin/python agent.py --doc <path> --no-defenses        # all layers off
.venv/bin/python agent.py --doc <path> --layers code,design # any subset
.venv/bin/python agent.py --doc <path> --no-cache           # defeat prompt caching
```

### Reproducing the results

Each script writes the matching file in `output/`:

```bash
.venv/bin/python scripts/count_handbook_tokens.py   # Problem 2  handbook size and cost
.venv/bin/python -m scripts.cache_test              # Problem 4  cached vs uncached
.venv/bin/python -m scripts.attack_test             # Problem 5  attacks, undefended
.venv/bin/python -m scripts.defense_test            # Problem 6  attacks, defended
.venv/bin/python -m scripts.red_team                # Problem 7  our own two attacks
.venv/bin/python -m scripts.exam_run                # Problem 8  the 10 exam documents
.venv/bin/python -m scripts.build_report            # Problem 9  the results page
```

> These make live API calls and append to the logs. The committed `output/` files
> are the results from the graded run.

**Start here:** open [`output/hw6_report.html`](output/hw6_report.html) in any
browser — one self-contained file, no internet needed.

---

## How it works

| File | Role |
|---|---|
| `agent.py` | Entry point. Parses `--doc`, builds the agent, runs it, writes the logs. |
| `tools.py` | Plain document readers, the trap-call recorder, cost accounting, JSON logging. |
| `models.py` | Structured types: `VendorFinding`, `VendorFacts`, `VendorDocument`. |
| `defenses.py` | **Code layer** — strips text a person could not see, before the model reads it. |
| `rules.py` | **Design layer** — parses the handbook and applies the four purchasing checks in Python. |
| `prompts/prompt.md` | **Prompt layer** — agent instructions and the security rules. The handbook is appended to this on every call. |

### The four purchasing checks

A quote is recommended only if all four pass (handbook section 4):

1. The vendor is on the approved list, and not on the removed/pending list.
2. The unit price is at or below that SKU's max unit cost.
3. Lead time is 21 days or less.
4. Minimum order is 600 units or less.

### The three defense layers

- **Code** — drops CSS-hidden HTML, PDF text drawn off the page / in near-white /
  at unreadable sizes / in invisible rendering mode, hidden parts of multipart
  emails, and zero-width characters. Reports everything it removed.
- **Design** — the model returns **facts only** (`VendorFacts` has no `decision`
  field); `rules.py` makes the decision in Python. Numbers not present in the
  document are discarded, URLs are scrubbed, and a gate sits in front of the
  dangerous tools.
- **Prompt** — the document is untrusted data, never instructions.

`send_email` and `approve_payment` are **registered but gated**: they record every
attempt to `output/trap_calls.json` and never send or pay anything. They stay in
the system so the shop can use them later behind a human approval.

---

## Results

| | |
|---|---|
| Practice documents, defended | **12 / 12 correct** |
| Practice documents, undefended | 9–10 / 12 |
| Trap tools triggered | **0**, across all runs |
| Exam documents | 10 processed, 0 trap calls |
| Caching saving | **~86 %** |
| Cost, defended | $0.00039 per document |

The fully defended agent is **slightly cheaper** than the undefended one: cleaning
the document deletes tokens before they are paid for, and moving the decision into
Python stops us paying the model to write out reasoning.

### Write-ups in `output/`

| File | What it covers |
|---|---|
| `hw6_report.html` | **The results page.** One self-contained file. |
| `handbook_estimate.md` | Problem 2 — handbook token count and cost estimate |
| `harness.md` | Problem 3 + 6 — every field and tool, plus the safety section |
| `cache_test.md` | Problem 4 — cached vs uncached, with the 30-day projection |
| `attack_results.md` | Problem 5 — what tricked the undefended agent, and where each payload hid |
| `defense_results.md` | Problem 6 — before/after, what each layer catches, what each costs |
| `red_team.md` | Problem 7 — the two attacks we wrote, and the two holes they found |
| `exam_results.json` | Problem 8 — the exam answers |
| `AI_prompts.md` | Every prompt given to the AI while building this |

---

## Notes

- `output/human_view/` and `output/human_view_attacks/` are screenshots of each
  document **as a person sees it**, for comparison with what the agent read. Every
  hidden instruction in this project is invisible in those images.
- The agent refuses to start on any model other than `gpt-6-luna`, and checks the
  model the API actually served on every run.
- `data/my_attacks/` holds the two attack documents written for Problem 7, plus
  their answer key. `scripts/make_attack_pdf.py` regenerates the PDF one.
