"""Tools and run-logging helpers for the vendor desk agent.

Three kinds of thing live here:

1. ``read_document`` - the only real tool. Reads HTML, PDF and .eml files.
2. ``send_email`` / ``approve_payment`` - trap tools. They never send anything;
   they only append the attempted call to output/trap_calls.json so we can tell
   whether a malicious document talked the agent into using them.
3. ``append_audit_event`` / ``append_usage_record`` - run logging.
"""

from __future__ import annotations

import email
import json
from datetime import datetime, timezone
from email import policy
from pathlib import Path

from bs4 import BeautifulSoup
from pypdf import PdfReader

from models import VendorDocument

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "output"
TRAP_CALLS_PATH = OUTPUT_DIR / "trap_calls.json"
AUDIT_TRAIL_PATH = OUTPUT_DIR / "audit_trail.json"
USAGE_LOG_PATH = OUTPUT_DIR / "usage_log.json"
PRICES_PATH = ROOT / "data" / "prices.json"


# --------------------------------------------------------------------------
# JSON list helpers
# --------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _append_json_list(path: Path, record: dict) -> None:
    """Append one record to a JSON file holding a list, creating it if needed."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        existing = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(existing, list):
            existing = []
    except (FileNotFoundError, json.JSONDecodeError):
        existing = []
    existing.append(record)
    path.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")


def ensure_output_files() -> None:
    """Make sure every output file exists and starts as an empty list."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in (TRAP_CALLS_PATH, AUDIT_TRAIL_PATH, USAGE_LOG_PATH):
        if not path.exists():
            path.write_text("[]\n", encoding="utf-8")


def append_audit_event(tool: str, args: dict, result: str) -> None:
    """Record one tool call, its arguments, and a short result."""
    _append_json_list(
        AUDIT_TRAIL_PATH,
        {"time": _now(), "kind": "tool_call", "tool": tool,
         "args": args, "result": result},
    )


def append_final_answer(doc: str, answer: dict) -> None:
    """Record the agent's final structured answer for this run."""
    _append_json_list(
        AUDIT_TRAIL_PATH,
        {"time": _now(), "kind": "final_answer", "document": doc, "answer": answer},
    )


# --------------------------------------------------------------------------
# Document reading
# --------------------------------------------------------------------------

def _read_html(path: Path) -> str:
    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="replace"), "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return soup.get_text("\n", strip=True)


def _read_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    return "\n".join((page.extract_text() or "") for page in reader.pages).strip()


def _read_eml(path: Path) -> str:
    msg = email.message_from_bytes(path.read_bytes(), policy=policy.default)
    headers = [f"{h}: {msg[h]}" for h in ("From", "To", "Subject", "Date") if msg[h]]
    body_part = msg.get_body(preferencelist=("plain", "html"))
    body = body_part.get_content() if body_part else ""
    if body_part is not None and body_part.get_content_type() == "text/html":
        body = BeautifulSoup(body, "html.parser").get_text("\n", strip=True)
    return "\n".join(headers) + "\n\n" + body.strip()


def read_document(path: str) -> VendorDocument:
    """Read one vendor document and return its plain text.

    Handles .html/.htm, .pdf and .eml; anything else is read as plain text.
    """
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    if not p.is_file():
        raise FileNotFoundError(f"No vendor document at {path}")

    suffix = p.suffix.lower()
    if suffix in (".html", ".htm"):
        doc_type, text = "html", _read_html(p)
    elif suffix == ".pdf":
        doc_type, text = "pdf", _read_pdf(p)
    elif suffix == ".eml":
        doc_type, text = "eml", _read_eml(p)
    else:
        doc_type, text = "text", p.read_text(encoding="utf-8", errors="replace")

    return VendorDocument(path=str(p), doc_type=doc_type, text=text)


# --------------------------------------------------------------------------
# Trap tools - these must never actually do anything
# --------------------------------------------------------------------------

def record_trap_call(tool: str, args: dict) -> str:
    """Log an attempted trap-tool call to output/trap_calls.json. Sends nothing."""
    _append_json_list(
        TRAP_CALLS_PATH, {"time": _now(), "tool": tool, "args": args}
    )
    return f"{tool} was recorded but NOT executed; no real action was taken."


# --------------------------------------------------------------------------
# Cost accounting
# --------------------------------------------------------------------------

def load_prices(model: str) -> dict:
    return json.loads(PRICES_PATH.read_text(encoding="utf-8"))[model]


def compute_cost(
    model: str,
    input_tokens: int,
    cached_input_tokens: int,
    output_tokens: int,
) -> dict:
    """Dollar cost for one call, using data/prices.json (prices are per 1M tokens)."""
    prices = load_prices(model)
    fresh_input = max(input_tokens - cached_input_tokens, 0)
    fresh_cost = fresh_input / 1_000_000 * prices["input_per_1m"]
    cached_cost = cached_input_tokens / 1_000_000 * prices["cached_input_per_1m"]
    output_cost = output_tokens / 1_000_000 * prices["output_per_1m"]
    return {
        "fresh_input_cost_usd": round(fresh_cost, 8),
        "cached_input_cost_usd": round(cached_cost, 8),
        "output_cost_usd": round(output_cost, 8),
        "total_cost_usd": round(fresh_cost + cached_cost + output_cost, 8),
    }


def append_usage_record(record: dict) -> None:
    _append_json_list(USAGE_LOG_PATH, record)
