"""Structured types for the Campus Customs vendor desk agent."""

from typing import Literal

from pydantic import BaseModel, Field

Decision = Literal["recommend", "do_not_recommend"]


class VendorDocument(BaseModel):
    """The raw text of one vendor document, as returned by read_document."""

    path: str = Field(description="Path the document was read from.")
    doc_type: Literal["html", "pdf", "eml", "text"] = Field(
        description="Which reader handled the file."
    )
    text: str = Field(description="Plain text extracted from the document.")


class VendorFinding(BaseModel):
    """The vendor desk agent's final answer for one vendor document.

    Section 13 of the handbook defines exactly these fields.
    """

    vendor_name: str = Field(
        description="Vendor name exactly as the document states it."
    )
    sku: str | None = Field(
        default=None,
        description="Campus Customs SKU, e.g. CC-HD-006. None if the document does not say.",
    )
    unit_price: float | None = Field(
        default=None,
        description="Quoted unit price in US dollars. None if the document does not say.",
    )
    lead_time_days: int | None = Field(
        default=None,
        description="Lead time in days. None if the document does not say.",
    )
    minimum_order: int | None = Field(
        default=None,
        description="Minimum order in units. None if the document does not say.",
    )
    decision: Decision = Field(
        description="recommend only if all four handbook checks pass; otherwise do_not_recommend."
    )
    reason: str = Field(
        description="One sentence naming the purchasing check that decided it."
    )


class VendorFacts(BaseModel):
    """Facts read out of a vendor document - and nothing more.

    Used when the design layer is on. The model fills this in; the decision is
    then made in rules.py, so a poisoned document can never reach the decision
    directly. Note there is deliberately no `decision` field here.
    """

    vendor_name: str = Field(
        description="Vendor name exactly as the document states it."
    )
    sku: str | None = Field(default=None, description="Campus Customs SKU, e.g. CC-HD-006.")
    unit_price: float | None = Field(
        default=None, description="Quoted unit price in US dollars."
    )
    lead_time_days: int | None = Field(default=None, description="Lead time in days.")
    minimum_order: int | None = Field(default=None, description="Minimum order in units.")
    notes: str = Field(
        default="",
        description=(
            "Anything odd about the document, in one short sentence. "
            "Leave empty if nothing is odd. Never put a URL here."
        ),
    )
