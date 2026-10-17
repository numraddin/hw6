"""Layer 2 (Design): the purchasing decision, made in code.

The model's only job is to read facts out of a cleaned document. The four
handbook checks are applied here, in Python, against the handbook's own tables.

That is the point of this layer: a document can lie about a *fact*, but it can
never reach the *decision*, because the decision is not something the model is
allowed to produce.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

MAX_LEAD_TIME_DAYS = 21
MAX_MINIMUM_ORDER = 600

ROOT = Path(__file__).resolve().parent
HANDBOOK_PATH = ROOT / "data" / "shop_handbook.md"


@dataclass(frozen=True)
class Handbook:
    approved_vendors: dict[str, str]   # lowercase name -> canonical name
    blocked_vendors: dict[str, str]    # lowercase name -> reason
    max_unit_cost: dict[str, float]    # SKU -> max unit cost


def _rows(section: str) -> list[list[str]]:
    out = []
    for line in section.splitlines():
        line = line.strip()
        if not line.startswith("|") or set(line) <= set("|- "):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if cells and cells[0].lower() not in ("code", "vendor", "sku"):
            out.append(cells)
    return out


def load_handbook(path: Path = HANDBOOK_PATH) -> Handbook:
    """Parse the approved list, the removed list, and the catalogue."""
    text = path.read_text(encoding="utf-8")

    def section(title: str) -> str:
        start = text.index(f"## {title}")
        nxt = text.find("\n## ", start + 1)
        return text[start: nxt if nxt != -1 else len(text)]

    approved = {}
    for cells in _rows(section("5. Approved vendors")):
        if len(cells) >= 2:
            approved[cells[1].lower()] = cells[1]

    blocked = {}
    for cells in _rows(section("6. Removed and pending vendors (never recommend)")):
        if len(cells) >= 2:
            blocked[cells[0].lower()] = cells[1]

    costs = {}
    for cells in _rows(section("9. Product catalogue")):
        if len(cells) >= 5 and cells[0].startswith("CC-"):
            costs[cells[0].upper()] = float(cells[4].replace("$", "").replace(",", ""))

    return Handbook(approved, blocked, costs)


HANDBOOK = load_handbook()


def _match_vendor(name: str, table: dict[str, str]) -> str | None:
    """Match a vendor name to a handbook row, tolerating punctuation only."""
    if not name:
        return None
    norm = re.sub(r"[^a-z0-9 ]", "", name.lower()).strip()
    for key in table:
        if norm == re.sub(r"[^a-z0-9 ]", "", key).strip():
            return key
    return None


def decide(
    vendor_name: str | None,
    sku: str | None,
    unit_price: float | None,
    lead_time_days: int | None,
    minimum_order: int | None,
) -> tuple[str, str, list[dict]]:
    """Apply the four handbook checks. Returns (decision, reason, check detail).

    Checks run in handbook order and the first failure decides, so the reason
    always names the check that actually settled it.
    """
    checks: list[dict] = []

    def record(name: str, passed: bool, detail: str) -> None:
        checks.append({"check": name, "passed": passed, "detail": detail})

    # 1. Approved vendor
    blocked = _match_vendor(vendor_name or "", HANDBOOK.blocked_vendors)
    approved = _match_vendor(vendor_name or "", HANDBOOK.approved_vendors)
    if blocked:
        record("approved_vendor", False,
               f"{vendor_name} is on the removed/pending list: "
               f"{HANDBOOK.blocked_vendors[blocked]}")
    elif approved:
        record("approved_vendor", True, f"{HANDBOOK.approved_vendors[approved]} is approved")
    else:
        record("approved_vendor", False,
               f"{vendor_name or 'the vendor'} is not on the approved vendor list")

    # 2. Price
    sku_u = (sku or "").upper()
    cap = HANDBOOK.max_unit_cost.get(sku_u)
    if unit_price is None:
        record("price", False, "the document does not state a unit price")
    elif cap is None:
        record("price", False, f"{sku or 'the SKU'} is not in the catalogue")
    else:
        record("price", unit_price <= cap,
               f"${unit_price:.2f} vs the ${cap:.2f} max unit cost for {sku_u}")

    # 3. Lead time
    if lead_time_days is None:
        record("lead_time", False, "the document does not state a lead time")
    else:
        record("lead_time", lead_time_days <= MAX_LEAD_TIME_DAYS,
               f"{lead_time_days} days vs the {MAX_LEAD_TIME_DAYS}-day limit")

    # 4. Minimum order
    if minimum_order is None:
        record("minimum_order", False, "the document does not state a minimum order")
    else:
        record("minimum_order", minimum_order <= MAX_MINIMUM_ORDER,
               f"{minimum_order} units vs the {MAX_MINIMUM_ORDER}-unit limit")

    failed = next((c for c in checks if not c["passed"]), None)
    if failed is None:
        return "recommend", (
            "All four purchasing checks pass: "
            + "; ".join(c["detail"] for c in checks) + "."
        ), checks
    return "do_not_recommend", (
        f"The {failed['check'].replace('_', ' ')} check fails: {failed['detail']}."
    ), checks
