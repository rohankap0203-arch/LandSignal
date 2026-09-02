"""Unit tests for user-initiated listing URL extraction (no live network)."""

from __future__ import annotations

from landsignal.services.listing_url import extract_listing_draft_from_html, missing_required


SAMPLE_HTML = """
<html><head>
<title>40 Acres in Riverside County, CA | Land.com</title>
<meta property="og:title" content="40 Acres Vacant Land — Riverside, CA" />
<meta property="og:description" content="Beautiful 40 acre parcel listed at $425,000 near Temecula." />
<script type="application/ld+json">
{
  "@type": "RealEstateListing",
  "name": "40 Acres Vacant Land — Riverside, CA",
  "description": "Vacant land opportunity",
  "offers": {"@type": "Offer", "price": "425000", "priceCurrency": "USD"},
  "address": {
    "@type": "PostalAddress",
    "addressLocality": "Temecula",
    "addressRegion": "CA"
  },
  "geo": {"@type": "GeoCoordinates", "latitude": 33.49, "longitude": -117.12}
}
</script>
</head><body>40 acres for sale</body></html>
"""


def test_extracts_jsonld_and_og():
    draft = extract_listing_draft_from_html(SAMPLE_HTML, url="https://www.land.com/property/123")
    assert draft["source_host"] == "Land.com family"
    assert draft["asking_price_usd"] == 425000
    assert draft["acreage"] == 40
    assert draft["state"] == "CA"
    assert draft["latitude"] == 33.49
    assert draft["longitude"] == -117.12
    assert not missing_required(draft)


def test_missing_when_thin():
    draft = extract_listing_draft_from_html("<html><head><title>x</title></head></html>", url="https://www.zillow.com/homedetails/1")
    assert draft["source_host"] == "Zillow"
    assert "acreage" in missing_required(draft)
