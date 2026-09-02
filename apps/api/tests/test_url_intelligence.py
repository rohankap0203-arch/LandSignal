"""Tests for Universal Listing URL Intelligence Engine."""

from __future__ import annotations

import pytest

from landsignal.services.listing_url import extract_listing_draft_from_html, missing_required
from landsignal.services.url_intelligence.conflicts import detect_acreage_conflict
from landsignal.services.url_intelligence.identity import resolve_identity
from landsignal.services.url_intelligence.semantic import semantic_extract
from landsignal.services.url_intelligence.ssrf import validate_listing_url
from landsignal.services.url_intelligence.confidence import compute_url_confidence
from landsignal.services.url_intelligence.adapters import select_adapter
from landsignal.services.url_intelligence.provenance import draft_from_fields


SAMPLE_HTML = """
<html><head>
<title>40 Acres in Riverside County, CA | Land.com</title>
<meta property="og:title" content="40 Acres Vacant Land — Riverside, CA" />
<meta property="og:description" content="Beautiful 40 acre parcel listed at $425,000 near Temecula. Electricity runs along County Road 18 approximately 400 feet from the eastern boundary. Seasonal creek crosses the southwest corner." />
<script type="application/ld+json">
{
  "@type": "RealEstateListing",
  "name": "40 Acres Vacant Land — Riverside, CA",
  "description": "Electricity runs along County Road 18 approximately 400 feet from the eastern boundary. Seasonal creek crosses the southwest corner.",
  "offers": {"@type": "Offer", "price": "425000", "priceCurrency": "USD"},
  "address": {
    "@type": "PostalAddress",
    "addressLocality": "Temecula",
    "addressRegion": "CA"
  },
  "geo": {"@type": "GeoCoordinates", "latitude": 33.49, "longitude": -117.12}
}
</script>
</head><body>40 acres for sale. APN: 123-456-789</body></html>
"""


def test_extracts_jsonld_and_og():
    draft = extract_listing_draft_from_html(SAMPLE_HTML, url="https://www.land.com/property/123")
    assert "Land.com" in draft["source_host"]
    assert draft["asking_price_usd"] == 425000
    assert draft["acreage"] == 40
    assert draft["state"] == "CA"
    assert draft["latitude"] == 33.49
    assert draft["longitude"] == -117.12
    assert not missing_required(draft)


def test_missing_when_thin():
    draft = extract_listing_draft_from_html(
        "<html><head><title>x</title></head></html>", url="https://www.zillow.com/homedetails/1"
    )
    assert draft["source_host"] == "Zillow"
    assert "acreage" in missing_required(draft)


def test_ssrf_blocks_localhost_and_metadata():
    assert validate_listing_url("http://127.0.0.1/admin")["ok"] is False
    assert validate_listing_url("http://localhost/x")["ok"] is False
    assert validate_listing_url("file:///etc/passwd")["ok"] is False
    assert validate_listing_url("http://169.254.169.254/latest/meta-data/")["ok"] is False
    assert validate_listing_url("https://www.land.com/property/1")["ok"] is True


def test_land_com_adapter_selected():
    adapter = select_adapter("https://www.land.com/property/1", "www.land.com")
    assert adapter.id == "land_com"


def test_semantic_electricity_and_creek():
    text = (
        "Electricity runs along County Road 18 approximately 400 feet from the eastern boundary. "
        "Seasonal creek crosses the southwest corner."
    )
    out = semantic_extract(text, source_url="https://example.com/listing")
    elec = out["utilities"]["electricity"]
    assert elec["status"]["value"] == "nearby"
    assert elec["distanceFeet"]["value"] == 400
    assert elec["distanceFeet"]["extractionMethod"] == "semantic_listing_extraction"
    assert "County Road" in str(elec.get("location", {}).get("value") or "")
    assert out["environment"]["surfaceWater"]["type"]["value"] == "seasonal_creek"


def test_identity_confidence_levels():
    fields = {
        "apn": {"value": "123-456", "confidence": 0.8},
        "latitude": {"value": 33.4, "confidence": 0.9},
        "longitude": {"value": -117.1, "confidence": 0.9},
        "state": {"value": "CA", "confidence": 0.95},
        "acreage": {"value": 40, "confidence": 0.9},
    }
    identity = resolve_identity(fields, draft_from_fields(fields))
    assert identity["propertyIdentityConfidence"] >= 70
    assert identity["state"] in {"VERIFIED", "HIGH_CONFIDENCE"}


def test_acreage_conflict_recorded():
    conflict = detect_acreage_conflict(42.1, 39.7)
    assert conflict is not None
    assert conflict["knowledgeState"] == "CONFLICTING"
    assert "42.1" in conflict["message"]
    assert "39.7" in conflict["message"]
    assert conflict["primary"]["source"] in {"listing", "parcel"}


def test_confidence_not_random():
    fields = {
        "askingPrice": {"value": 100000, "confidence": 0.95},
        "acreage": {"value": 34.2, "confidence": 0.9},
        "title": {"value": "Land", "confidence": 0.9},
        "state": {"value": "CA", "confidence": 0.95},
    }
    identity = {"propertyIdentityConfidence": 80}
    a = compute_url_confidence(
        fields=fields,
        identity=identity,
        conflicts=[],
        fetch_status="ok",
        semantic={},
        enrichment_present=True,
    )
    b = compute_url_confidence(
        fields=fields,
        identity=identity,
        conflicts=[],
        fetch_status="ok",
        semantic={},
        enrichment_present=True,
    )
    assert a["overall"] == b["overall"]
    assert a["overall"] > 50
    assert "Parcel Identity" in a["categories"]


@pytest.mark.asyncio
async def test_extract_pipeline_from_html(monkeypatch):
    from landsignal.services.url_intelligence import pipeline as pipe

    async def fake_fetch(url: str):
        return SAMPLE_HTML, "ok", url

    monkeypatch.setattr(pipe, "_fetch_html", fake_fetch)
    result = await pipe.extract_listing_intelligence("https://www.land.com/property/abc")
    assert result["ok"] is True
    assert result["draft"]["acreage"] == 40
    assert result["draft"]["asking_price_usd"] == 425000
    assert result["identity"]["propertyIdentityConfidence"] >= 50
    assert any(s["id"] == "reading_listing" and s["status"] == "done" for s in result["stages"])
    assert any("acres" in f.lower() for f in result["facts"])
    # semantic nested under fields
    assert "utilities" in result["fields"] or "utilities" in (result.get("semantic") or {})


def test_url_slug_hints():
    from landsignal.services.url_intelligence.url_hints import extract_from_listing_url

    land = extract_from_listing_url(
        "https://www.land.com/property/40-acres-in-riverside-county-california/221012345/"
    )
    assert land["acreage"] == 40.0
    assert land["state"] == "CA"
    assert land["county"] == "Riverside"

    watch = extract_from_listing_url(
        "https://www.landwatch.com/kern-county-california-34-acres/pid/401234567"
    )
    assert watch["acreage"] == 34.0
    assert watch["county"] == "Kern"
    assert watch["state"] == "CA"

    bernardino = extract_from_listing_url(
        "https://www.land.com/property/118-acres-in-san-bernardino-county-california/x/"
    )
    assert bernardino["county"] == "San Bernardino"
    assert bernardino["acreage"] == 118.0

    # Singular "40-acre", query params, embedded coords
    singular = extract_from_listing_url(
        "https://example.com/listings/40-acre-ranch-kern-ca?lat=35.1321&lng=-118.4482&price=118000"
    )
    assert singular["acreage"] == 40.0
    assert singular["latitude"] == 35.1321
    assert singular["longitude"] == -118.4482
    assert singular["asking_price_usd"] == 118000

    acres_param = extract_from_listing_url("https://broker.example/lot?acreage=12.5&state=TX&county=Travis")
    assert acres_param["acreage"] == 12.5
    assert acres_param["state"] == "TX"
    assert acres_param["county"] == "Travis"


def test_material_missing_does_not_block_on_acreage_alone():
    from landsignal.services.url_intelligence.pipeline import material_missing

    # Coords + state present → empty material list even without acreage
    assert material_missing({"state": "CA", "latitude": 35.1, "longitude": -118.4, "title": "x"}) == []
    # No location at all → asks for coordinates (and maybe state)
    fields = {m["field"] for m in material_missing({"title": "x"})}
    assert "coordinates" in fields
