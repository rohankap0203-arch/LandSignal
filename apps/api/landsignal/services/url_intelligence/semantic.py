"""Deterministic semantic extraction from listing description text.

Produces provenanced structured attributes (utilities, water, access, etc.).
Pattern-based so every field carries sourceText — no external LLM required.
"""

from __future__ import annotations

import re
from typing import Any

from landsignal.services.url_intelligence.provenance import provenanced


def _p(value: Any, text: str, *, confidence: float, source_url: str | None, unit: str | None = None) -> dict[str, Any]:
    return provenanced(
        value,
        source="AI_extraction",
        confidence=confidence,
        extraction_method="semantic_listing_extraction",
        source_url=source_url,
        source_text=text,
        unit=unit,
    )


def _merge(dst: dict[str, Any], src: dict[str, Any]) -> dict[str, Any]:
    for k, v in src.items():
        if k in dst and isinstance(dst[k], dict) and isinstance(v, dict):
            _merge(dst[k], v)
        else:
            dst[k] = v
    return dst


def semantic_extract(description: str | None, *, source_url: str | None = None) -> dict[str, Any]:
    """Extract structured attributes from free-text listing description."""
    text = (description or "").strip()
    if not text or len(text) < 20:
        return {}

    out: dict[str, Any] = {}

    for m in re.finditer(
        r"(?:electric(?:ity)?|power)\s+[^.!?]{0,80}?(?:approximately|about|roughly|~)?\s*"
        r"([0-9]{2,5}(?:,[0-9]{3})?)\s*(?:feet|ft\.?)"
        r"(?:\s+from\s+(?:the\s+)?([^.!?]{3,40}))?",
        text,
        re.I,
    ):
        feet = float(m.group(1).replace(",", ""))
        pos = (m.group(2) or "").strip() or None
        loc_m = re.search(r"(?:along|on|near)\s+([^,]{3,40})", m.group(0), re.I)
        loc = loc_m.group(1).strip() if loc_m else None
        elec: dict[str, Any] = {
            "status": _p("nearby", m.group(0), confidence=0.88, source_url=source_url),
            "distanceFeet": _p(feet, m.group(0), confidence=0.91, source_url=source_url, unit="feet"),
        }
        if loc:
            elec["location"] = _p(loc, m.group(0), confidence=0.8, source_url=source_url)
        if pos:
            elec["relativePosition"] = _p(pos, m.group(0), confidence=0.78, source_url=source_url)
        _merge(out, {"utilities": {"electricity": elec}})
        break

    if re.search(
        r"\belectric(?:ity)?\s+(?:is\s+)?(?:on[- ]site|at\s+the\s+property|to\s+the\s+(?:property|parcel))\b",
        text,
        re.I,
    ):
        m = re.search(r".{0,50}electric.{0,50}", text, re.I)
        snippet = m.group(0) if m else "electricity on site"
        _merge(
            out,
            {
                "utilities": {
                    "electricity": {
                        "status": _p("on_site", snippet, confidence=0.9, source_url=source_url),
                    }
                }
            },
        )

    for m in re.finditer(
        r"seasonal\s+creek[^.!?]{0,50}?(?:(?:crosses|in|at)\s+(?:the\s+)?([\w\s]+corner|[\w\s]+boundary))?",
        text,
        re.I,
    ):
        corner = (m.group(1) or "").strip() or None
        block: dict[str, Any] = {
            "type": _p("seasonal_creek", m.group(0), confidence=0.86, source_url=source_url),
        }
        if corner:
            block["location"] = _p(corner, m.group(0), confidence=0.8, source_url=source_url)
        _merge(out, {"environment": {"surfaceWater": block}})
        break

    for m in re.finditer(r"\b(?:has\s+a\s+)?(?:water\s+)?well\b|\bno\s+well\b", text, re.I):
        status = "absent" if "no well" in m.group(0).lower() else "present"
        _merge(
            out,
            {
                "utilities": {
                    "wells": {"status": _p(status, m.group(0), confidence=0.84, source_url=source_url)}
                }
            },
        )
        break

    for m in re.finditer(r"\bseptic\b|\bperc\s+test\b", text, re.I):
        low = m.group(0).lower()
        status = "perc_mentioned" if "perc" in low else "mentioned"
        if "has septic" in text.lower() or "septic on" in text.lower():
            status = "present"
        _merge(
            out,
            {
                "utilities": {
                    "septic": {"status": _p(status, m.group(0), confidence=0.82, source_url=source_url)}
                }
            },
        )
        break

    for m in re.finditer(
        r"([0-9]{2,5}(?:,[0-9]{3})?)\s*(?:feet|ft\.?)\s+of\s+(?:road\s+)?frontage",
        text,
        re.I,
    ):
        feet = float(m.group(1).replace(",", ""))
        _merge(
            out,
            {
                "access": {
                    "roadFrontageFeet": _p(
                        feet, m.group(0), confidence=0.87, source_url=source_url, unit="feet"
                    )
                }
            },
        )
        break

    for m in re.finditer(r"(?:not\s+in\s+a\s+flood|no\s+flood|flood\s*zone|floodplain)", text, re.I):
        low = m.group(0).lower()
        if "not in a flood" in low or "no flood" in low:
            status = "not_in_floodplain"
        else:
            status = "mentioned"
        _merge(
            out,
            {
                "hazards": {
                    "flood": {
                        "listingClaim": _p(status, m.group(0), confidence=0.75, source_url=source_url)
                    }
                }
            },
        )
        break

    for m in re.finditer(r"\bwetlands?\b", text, re.I):
        _merge(
            out,
            {
                "hazards": {
                    "wetlands": {
                        "listingClaim": _p("mentioned", m.group(0), confidence=0.78, source_url=source_url)
                    }
                }
            },
        )
        break

    for m in re.finditer(r"\b(?:no\s+hoa|hoa[- ]free|hoa\b)", text, re.I):
        low = m.group(0).lower()
        status = "none" if "no hoa" in low or "hoa-free" in low or "hoa free" in low else "present"
        _merge(
            out,
            {
                "restrictions": {
                    "hoa": _p(status, m.group(0), confidence=0.85, source_url=source_url)
                }
            },
        )
        break

    return out
