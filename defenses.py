"""Layer 1 (Code): make a document safe *before* any model sees it.

Every reader here keeps only the text a human would actually see when the
document is opened normally, and reports everything it removed.

The three readers mirror the three ways the practice documents hide text:

* HTML - CSS that makes text invisible (``display:none``, ``font-size:0``,
  white-on-white, ``opacity:0``, ``visibility:hidden``) and HTML comments.
* PDF  - text drawn outside the page box, in a near-background colour, or at a
  font size too small to read. Found by walking the content stream, because
  ``pypdf.extract_text()`` reports all three as ordinary text.
* EML  - the same HTML tricks inside a ``text/html`` alternative part, plus
  zero-width characters used to break up keywords.
"""

from __future__ import annotations

import email
import re
import unicodedata
from dataclasses import dataclass, field
from email import policy
from pathlib import Path

from bs4 import BeautifulSoup, Comment
from pypdf import PdfReader

# Text smaller than this is unreadable in a normal viewer.
MIN_FONT_SIZE_PT = 4.0
# A fill colour at least this bright counts as "white on white".
NEAR_WHITE = 0.90
# Characters with no visual width, used to break up words like "C​o​r​r".
INVISIBLE_CHARS = dict.fromkeys(
    [0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF, 0x00AD, 0x180E], None
)


@dataclass
class CleanedDocument:
    """What the code layer hands to the rest of the agent."""

    path: str
    doc_type: str
    text: str
    removed: list[dict] = field(default_factory=list)

    @property
    def suspicious(self) -> bool:
        return bool(self.removed)

    def summary(self) -> str:
        if not self.removed:
            return "no hidden content found"
        kinds = sorted({r["reason"] for r in self.removed})
        return f"{len(self.removed)} hidden span(s) removed ({', '.join(kinds)})"


def _strip_invisible(text: str) -> tuple[str, bool]:
    """Remove zero-width characters and normalise unicode look-alikes."""
    cleaned = text.translate(INVISIBLE_CHARS)
    cleaned = unicodedata.normalize("NFKC", cleaned)
    return cleaned, cleaned != text


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

_SIZE_RE = re.compile(r"font-size\s*:\s*([0-9.]+)\s*(px|pt|em|rem)?", re.I)
_COLOR_RE = re.compile(r"(?<!-)\bcolor\s*:\s*([^;]+)", re.I)
_OPACITY_RE = re.compile(r"opacity\s*:\s*([0-9.]+)", re.I)


def _hidden_reason(style: str) -> str | None:
    """Why this inline style makes text invisible, or None if it does not."""
    s = style.lower().replace(" ", "")
    if "display:none" in s:
        return "css display:none"
    if "visibility:hidden" in s:
        return "css visibility:hidden"

    m = _SIZE_RE.search(style)
    if m:
        value = float(m.group(1))
        unit = (m.group(2) or "px").lower()
        px = value * {"px": 1, "pt": 1.333, "em": 16, "rem": 16}[unit]
        if px < MIN_FONT_SIZE_PT:
            return f"css font-size {m.group(1)}{unit}"

    m = _OPACITY_RE.search(style)
    if m and float(m.group(1)) < 0.1:
        return "css opacity 0"

    m = _COLOR_RE.search(style)
    if m:
        colour = m.group(1).strip().lower()
        if colour in ("#fff", "#ffffff", "white", "rgb(255,255,255)"):
            return "white text on white background"

    if "text-indent:-" in s or "left:-9999" in s:
        return "css off-screen positioning"
    return None


_RULE_RE = re.compile(r"([^{}]+)\{([^{}]*)\}")


def _stylesheet_rules(soup: BeautifulSoup) -> list[tuple[str, str]]:
    """Selectors in <style> blocks whose body hides text.

    Added after Problem 7: an attacker can put `display:none` in a stylesheet
    and reference it by class, which an inline-style check never sees.
    """
    hidden = []
    for block in soup.find_all("style"):
        for selector_group, body in _RULE_RE.findall(block.get_text()):
            reason = _hidden_reason(body)
            if reason:
                for selector in selector_group.split(","):
                    hidden.append((selector.strip(), f"{reason} (via <style> block)"))
    return hidden


def _matches(tag, selector: str) -> bool:
    """Tag-name / .class / #id selectors, optionally combined (e.g. tr.foo)."""
    try:
        return tag in tag.parent.select(selector) if tag.parent else False
    except Exception:
        return False


def clean_html(markup: str) -> tuple[str, list[dict]]:
    """Return the visible text of an HTML document and what was removed."""
    soup = BeautifulSoup(markup, "html.parser")
    removed: list[dict] = []

    # Stylesheet-driven hiding has to be resolved before <style> is discarded.
    for selector, reason in _stylesheet_rules(soup):
        try:
            targets = soup.select(selector)
        except Exception:
            continue
        for tag in targets:
            body = tag.get_text(" ", strip=True)
            if body:
                removed.append({"reason": reason, "text": body[:400]})
            tag.decompose()

    for node in soup.find_all(string=lambda t: isinstance(t, Comment)):
        text = node.strip()
        if text:
            removed.append({"reason": "html comment", "text": text[:400]})
        node.extract()

    for tag in soup(["script", "style", "noscript", "head"]):
        # Scripts and styles are never visible prose. Only report ones that
        # look like they are addressing a reader.
        body = tag.get_text(" ", strip=True)
        if tag.name in ("script", "noscript") and len(body) > 120:
            removed.append({"reason": f"<{tag.name}> content", "text": body[:400]})
        tag.decompose()

    for tag in soup.find_all(style=True):
        reason = _hidden_reason(tag.get("style", ""))
        if reason:
            body = tag.get_text(" ", strip=True)
            if body:
                removed.append({"reason": reason, "text": body[:400]})
            tag.decompose()

    for tag in soup.find_all(hidden=True):
        body = tag.get_text(" ", strip=True)
        if body:
            removed.append({"reason": "hidden attribute", "text": body[:400]})
        tag.decompose()

    text, had_invisible = _strip_invisible(soup.get_text("\n", strip=True))
    if had_invisible:
        removed.append({"reason": "zero-width characters", "text": "(stripped in place)"})
    return text, removed


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

_TM_RE = re.compile(r"([-\d.]+)\s+([-\d.]+)\s+Tm")
_TF_RE = re.compile(r"/\w+\s+([\d.]+)\s+Tf")
_RG_RE = re.compile(r"(?:^|\s)([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+rg")
_G_RE = re.compile(r"(?:^|\s)([\d.]+)\s+g(?:\s|$)")
def _scan_strings(line: str) -> list[tuple[int, str]]:
    """Find every `(...) Tj` in a content-stream line.

    Written as a scanner rather than a regex because PDF strings may contain
    *balanced* unescaped parentheses - "(Payment terms (net 30))" is one legal
    string. A regex that stops at the first ")" silently truncates such a line,
    which would drop real text out of a clean quote.
    """
    out: list[tuple[int, str]] = []
    i = 0
    while i < len(line):
        if line[i] != "(":
            i += 1
            continue
        start, depth, buf = i, 0, []
        while i < len(line):
            ch = line[i]
            if ch == "\\" and i + 1 < len(line):
                buf.append(line[i + 1])
                i += 2
                continue
            if ch == "(":
                depth += 1
                if depth > 1:
                    buf.append(ch)
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    i += 1
                    break
                buf.append(ch)
            else:
                buf.append(ch)
            i += 1
        if re.match(r"\s*Tj", line[i:]):
            out.append((start, "".join(buf)))
    return out

# Text rendering mode. "3 Tr" means fill nothing and stroke nothing: the
# glyphs are in the file and every extractor reports them, but a viewer
# paints absolutely nothing. This is how a scanner hides an OCR text layer
# behind a page image - and how a02 in data/my_attacks hides its payload.
_TR_RE = re.compile(r"(?:^|\s)([0-7])\s+Tr(?:\s|$)")
INVISIBLE_RENDER_MODES = {3, 7}


def clean_pdf(path: Path) -> tuple[str, list[dict]]:
    """Return the *visible* text of a PDF and what was dropped.

    Walks the content stream tracking the current text position, font size and
    fill colour, so text that a viewer would never paint is dropped.
    """
    reader = PdfReader(str(path))
    kept: list[str] = []
    removed: list[dict] = []

    for page in reader.pages:
        box = page.mediabox
        x0, y0 = float(box.left), float(box.bottom)
        x1, y1 = float(box.right), float(box.top)

        content = page.get_contents()
        if content is None:
            continue
        stream = content.get_data().decode("latin-1", errors="replace")

        size, brightness, pos, render_mode = 12.0, 0.0, (0.0, 0.0), 0
        for line in stream.split("\n"):
            if (m := _TF_RE.search(line)):
                size = float(m.group(1))
            # Tr changes are positional: a line can turn invisible mode on,
            # draw, and turn it off again, so the mode in force for each Tj
            # has to be read from the operators to its left.
            tr_marks = [(m.start(), int(m.group(1))) for m in _TR_RE.finditer(line)]
            if (m := _RG_RE.search(line)):
                r, g, b = (float(m.group(i)) for i in (1, 2, 3))
                brightness = min(r, g, b)
            elif (m := _G_RE.search(line)):
                brightness = float(m.group(1))
            if (m := _TM_RE.search(line)):
                pos = (float(m.group(1)), float(m.group(2)))

            for at, text in _scan_strings(line):
                if not text.strip():
                    continue
                x, y = pos
                mode = render_mode
                for pos_tr, value in tr_marks:
                    if pos_tr < at:
                        mode = value
                if mode in INVISIBLE_RENDER_MODES:
                    removed.append({
                        "reason": f"invisible text rendering mode ({mode} Tr)",
                        "text": text[:400]})
                elif not (x0 - 1 <= x <= x1 + 1 and y0 - 1 <= y <= y1 + 1):
                    removed.append({
                        "reason": f"drawn off the page (y={y:g})", "text": text[:400]})
                elif brightness >= NEAR_WHITE:
                    removed.append({
                        "reason": "near-white text on white background", "text": text[:400]})
                elif size < MIN_FONT_SIZE_PT:
                    removed.append({
                        "reason": f"font size {size:g}pt (unreadable)", "text": text[:400]})
                else:
                    kept.append(text)

            if tr_marks:
                render_mode = tr_marks[-1][1]

    text = "\n".join(kept).strip()
    if not text:
        # The scanner did not understand this PDF. Fall back to pypdf so a
        # clean document is never blanked out, and say so loudly.
        text = "\n".join((p.extract_text() or "") for p in reader.pages).strip()
        removed.append({
            "reason": "SCANNER FALLBACK - could not verify what is visible",
            "text": "(hidden-text checks did not run on this PDF)"})

    text, had_invisible = _strip_invisible(text)
    if had_invisible:
        removed.append({"reason": "zero-width characters", "text": "(stripped in place)"})
    return text, removed


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------

def clean_eml(path: Path) -> tuple[str, list[dict]]:
    """Return the visible text of an email, checking *every* alternative part.

    The plain-text part is used as the body, but the HTML alternative is
    sanitised too: an attacker can hide text in the part the reader does not
    happen to open.
    """
    msg = email.message_from_bytes(path.read_bytes(), policy=policy.default)
    removed: list[dict] = []

    headers = [f"{h}: {msg[h]}" for h in ("From", "To", "Subject", "Date") if msg[h]]

    plain, html = None, None
    for part in msg.walk():
        ctype = part.get_content_type()
        if ctype == "text/plain" and plain is None:
            plain = part.get_content()
        elif ctype == "text/html" and html is None:
            html = part.get_content()

    html_text = None
    if html is not None:
        html_text, html_removed = clean_html(html)
        removed.extend(
            {**r, "reason": f"{r['reason']} (in text/html part)"} for r in html_removed
        )

    body = plain if plain is not None else (html_text or "")
    text, had_invisible = _strip_invisible("\n".join(headers) + "\n\n" + body.strip())
    if had_invisible:
        removed.append({"reason": "zero-width characters", "text": "(stripped in place)"})
    return text, removed


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def clean_document(path: str | Path, root: Path | None = None) -> CleanedDocument:
    """Read one vendor document, keeping only what a person would see."""
    p = Path(path)
    if not p.is_absolute() and root is not None:
        p = root / p
    if not p.is_file():
        raise FileNotFoundError(f"No vendor document at {path}")

    suffix = p.suffix.lower()
    if suffix in (".html", ".htm"):
        doc_type = "html"
        text, removed = clean_html(p.read_text(encoding="utf-8", errors="replace"))
    elif suffix == ".pdf":
        doc_type = "pdf"
        text, removed = clean_pdf(p)
    elif suffix == ".eml":
        doc_type = "eml"
        text, removed = clean_eml(p)
    else:
        doc_type = "text"
        text, removed = _strip_invisible(p.read_text(encoding="utf-8", errors="replace"))[0], []

    return CleanedDocument(path=str(p), doc_type=doc_type, text=text, removed=removed)


# ---------------------------------------------------------------------------
# Output checks (used by the design layer)
# ---------------------------------------------------------------------------

_URL_RE = re.compile(r"https?://\S+|www\.\S+|\b\S+\.(?:example|com|net|org)\b", re.I)


def scrub_text(text: str) -> tuple[str, list[str]]:
    """Strip URLs out of free text headed for the buyer. Returns (text, removed)."""
    found = _URL_RE.findall(text or "")
    if not found:
        return text or "", []
    return _URL_RE.sub("[link removed]", text), found


def ground_facts(facts: dict, source_text: str) -> tuple[dict, list[str]]:
    """Drop any number the cleaned document does not actually contain.

    The model can hallucinate or be talked into a value. A number that is not
    present in the visible text of the document is not a fact about it, so it
    is discarded rather than trusted.
    """
    checked = dict(facts)
    ungrounded: list[str] = []
    haystack = source_text.replace(",", "")

    for field_name in ("unit_price", "lead_time_days", "minimum_order"):
        value = checked.get(field_name)
        if value is None:
            continue
        if field_name == "unit_price":
            candidates = [f"{value:.2f}", f"{value:g}"]
        else:
            candidates = [str(int(value)), f"{value:g}"]
        if not any(c in haystack for c in candidates):
            ungrounded.append(f"{field_name}={value}")
            checked[field_name] = None

    return checked, ungrounded
