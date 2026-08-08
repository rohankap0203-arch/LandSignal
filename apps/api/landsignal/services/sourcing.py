"""Where each parcel came from + how a buyer actually reaches the seller/office."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote_plus

# Concrete offices for feeds we ingest. Phones/URLs are public agency contacts.
# Keys: (provider_id, STATE, county_normalized) — county matched case-insensitive contains.
OFFICES: list[dict[str, Any]] = [
    {
        "provider_id": "public_tax_sale",
        "state": "IN",
        "county": "marion",
        "source_name": "Indianapolis / Marion County tax sale (public GIS)",
        "office": "Marion County Treasurer — Tax Sale",
        "website": "https://www.indy.gov/activity/property-tax-sale",
        "phone": "317-327-4040",
        "parcel_lookup": "https://maps.indy.gov/AssessorPropertyViewer/",
        "how": "Register for the county tax sale; bids start at the published minimum, not a retail ask.",
    },
    {
        "provider_id": "public_tax_sale",
        "state": "CA",
        "county": "shasta",
        "source_name": "Shasta County CA tax auction GIS",
        "office": "Shasta County Treasurer-Tax Collector",
        "website": "https://www.shastacounty.gov/treasurer-tax-collector",
        "phone": "530-225-5511",
        "parcel_lookup": "https://gis.shastacounty.gov/",
        "how": "Watch the Treasurer tax-auction calendar; minimum bid is on the county layer.",
    },
    {
        "provider_id": "public_tax_sale",
        "state": "WI",
        "county": "sauk",
        "source_name": "Sauk County WI parcels for sale GIS",
        "office": "Sauk County Land Records / Treasurer",
        "website": "https://lrs.co.sauk.wi.us/AscentLandRecords/",
        "phone": "608-355-3286",
        "parcel_lookup": "https://lrs.co.sauk.wi.us/AscentLandRecords/",
        "how": "County land-records GIS marks parcels offered for sale — contact Treasurer to bid/buy.",
    },
    {
        "provider_id": "public_tax_sale",
        "state": "KS",
        "county": "wyandotte",
        "source_name": "Wyandotte County / UG tax-sale eligible GIS",
        "office": "Unified Government of Wyandotte County Treasurer",
        "website": "https://www.wycokck.org/Departments/Treasury",
        "phone": "913-573-2821",
        "parcel_lookup": "https://gisweb.wycokck.org/",
        "how": "Tax-sale eligible layer — confirm current sale status with the Treasurer before bidding.",
    },
    {
        "provider_id": "public_tax_sale",
        "state": "OH",
        "county": "mahoning",
        "source_name": "Mahoning County OH delinquent / land-bank GIS",
        "office": "Mahoning County Treasurer / Land Bank",
        "website": "https://www.mahoningcountyoh.gov/",
        "phone": "330-740-2460",
        "parcel_lookup": "https://gisapp.mahoningcountyoh.gov/",
        "how": "Delinquent / land-bank inventory — call Treasurer or land bank for acquisition path.",
    },
    {
        "provider_id": "public_tax_sale",
        "state": "AZ",
        "county": "cochise",
        "source_name": "Cochise County AZ tax-lien parcel GIS",
        "office": "Cochise County Treasurer",
        "website": "https://www.cochise.az.gov/205/Treasurer",
        "phone": "520-432-8400",
        "parcel_lookup": "https://www.cochise.az.gov/",
        "how": "Tax-lien parcel layer — Treasurer runs lien/deed sales; verify year and status.",
    },
    {
        "provider_id": "public_tax_sale",
        "state": "GA",
        "county": "dekalb",
        "source_name": "DeKalb County GA delinquent parcel GIS",
        "office": "DeKalb County Tax Commissioner",
        "website": "https://www.dekalbtax.org/",
        "phone": "404-298-4000",
        "parcel_lookup": "https://www.dekalbtax.org/",
        "how": "Delinquent inventory — Tax Commissioner / tax sale calendar is the buy path.",
    },
    {
        "provider_id": "public_tax_sale",
        "state": "PA",
        "county": "allegheny",
        "source_name": "Allegheny County PA public parcel GIS",
        "office": "Allegheny County Real Estate / Treasurer",
        "website": "https://www.alleghenycounty.us/treasurer/index.aspx",
        "phone": "412-350-4100",
        "parcel_lookup": "https://www.alleghenycounty.us/real-estate/index.aspx",
        "how": "Public parcel screen (≥2 ac). Confirm if on upset/tax sale with Treasurer.",
    },
    {
        "provider_id": "public_tax_sale",
        "state": "TX",
        "county": "dallas",
        "source_name": "Dallas CAD vacant tracts (public GIS)",
        "office": "Dallas Central Appraisal District",
        "website": "https://www.dallascad.org/",
        "phone": "214-631-0910",
        "parcel_lookup": "https://www.dallascad.org/",
        "how": "Vacant CAD inventory — not a live MLS ask. Look up account on DCAD, then owner/broker.",
    },
    {
        "provider_id": "public_tax_sale",
        "state": "TX",
        "county": "bexar",
        "source_name": "Bexar County CAD vacant land GIS",
        "office": "Bexar Appraisal District",
        "website": "https://www.bcad.org/",
        "phone": "210-242-2432",
        "parcel_lookup": "https://www.bcad.org/",
        "how": "Vacant land screen from CAD. Owner on account; no retail list price on this feed.",
    },
    {
        "provider_id": "public_tax_sale",
        "state": "WA",
        "county": "king",
        "source_name": "King County WA vacant property GIS",
        "office": "King County Department of Assessments",
        "website": "https://www.kingcounty.gov/depts/assessor.aspx",
        "phone": "206-296-7300",
        "parcel_lookup": "https://blue.kingcounty.com/Assessor/eRealProperty/default.aspx",
        "how": "Vacant land from county property info — look up PIN for owner/mailing contact.",
    },
    {
        "provider_id": "public_tax_sale",
        "state": "TN",
        "county": "davidson",
        "source_name": "Davidson County / Nashville vacant cadastral GIS",
        "office": "Metro Nashville Assessor of Property",
        "website": "https://www.nashville.gov/departments/assessor-property",
        "phone": "615-862-6080",
        "parcel_lookup": "https://www.padctn.org/",
        "how": "Vacant rural/land screen — PAD lookup for owner; no published retail ask on this feed.",
    },
    {
        "provider_id": "public_tax_sale",
        "state": "MI",
        "county": "wayne",
        "source_name": "Detroit Land Bank Authority inventory",
        "office": "Detroit Land Bank Authority",
        "website": "https://buildingdetroit.org/",
        "phone": "313-974-6869",
        "parcel_lookup": "https://buildingdetroit.org/properties/",
        "how": "DLBA for-sale / side-lot inventory — buy through buildingdetroit.org programs.",
    },
    {
        "provider_id": "public_tax_sale",
        "state": "UT",
        "county": "",
        "source_name": "Utah tax sale parcels (public ArcGIS)",
        "office": "County Treasurer (Utah tax sale)",
        "website": "https://tax.utah.gov/",
        "phone": "801-297-2200",
        "parcel_lookup": "https://tax.utah.gov/",
        "how": "Active tax-sale layer — contact the county Treasurer listed on the parcel for auction rules.",
    },
    {
        "provider_id": "public_tax_sale",
        "state": "IL",
        "county": "whiteside",
        "source_name": "Whiteside County IL tax foreclosure GIS",
        "office": "Whiteside County Treasurer",
        "website": "https://www.whiteside.org/treasurer/",
        "phone": "815-772-5196",
        "parcel_lookup": "https://www.whiteside.org/",
        "how": "Foreclosure / tax-parcel records — Treasurer for sale status and bidding.",
    },
    {
        "provider_id": "public_surplus",
        "state": "NC",
        "county": "brunswick",
        "source_name": "Brunswick County NC surplus property GIS",
        "office": "Brunswick County Surplus / Administration",
        "website": "https://www.brunswickcountync.gov/",
        "phone": "910-253-2000",
        "parcel_lookup": "https://www.brunswickcountync.gov/",
        "how": "County surplus layer — procurement / surplus office handles offers.",
    },
    {
        "provider_id": "public_surplus",
        "state": "FL",
        "county": "broward",
        "source_name": "Fort Lauderdale surplus property GIS",
        "office": "City of Fort Lauderdale Surplus Property",
        "website": "https://www.fortlauderdale.gov/",
        "phone": "954-828-5000",
        "parcel_lookup": "https://www.fortlauderdale.gov/",
        "how": "Municipal surplus — city real estate / surplus desk is the seller.",
    },
    {
        "provider_id": "public_surplus",
        "state": "VA",
        "county": "fairfax",
        "source_name": "Fairfax County VA large parcel GIS",
        "office": "Fairfax County Department of Tax Administration",
        "website": "https://www.fairfaxcounty.gov/taxes/",
        "phone": "703-222-8234",
        "parcel_lookup": "https://www.fairfaxcounty.gov/realestate/",
        "how": "Large-parcel screen from open data — look up PIN for owner; not a dedicated surplus sale.",
    },
    {
        "provider_id": "blm_lpad",
        "state": "",
        "county": "",
        "source_name": "BLM Lands Potentially Available for Disposal (LPAD)",
        "office": "Bureau of Land Management — Lands & Realty",
        "website": "https://www.blm.gov/programs/lands-and-realty/land-tenure",
        "phone": "202-208-3801",
        "parcel_lookup": "https://www.blm.gov/services/land-records",
        "how": "Federal disposal / sale-exchange under FLPMA — contact the BLM field office for the admin state.",
    },
]

BLM_STATE_OFFICES = {
    "AK": ("https://www.blm.gov/alaska", "907-271-5960"),
    "AZ": ("https://www.blm.gov/arizona", "602-417-9200"),
    "CA": ("https://www.blm.gov/california", "916-978-4400"),
    "CO": ("https://www.blm.gov/colorado", "303-239-3600"),
    "ID": ("https://www.blm.gov/idaho", "208-373-4000"),
    "MT": ("https://www.blm.gov/montana-dakotas", "406-896-5000"),
    "NM": ("https://www.blm.gov/new-mexico", "505-954-2000"),
    "NV": ("https://www.blm.gov/nevada", "775-861-6400"),
    "OR": ("https://www.blm.gov/oregon-washington", "503-808-6001"),
    "UT": ("https://www.blm.gov/utah", "801-539-4001"),
    "WY": ("https://www.blm.gov/wyoming", "307-775-6256"),
    "WA": ("https://www.blm.gov/oregon-washington", "503-808-6001"),
}


def resolve_office(
    *,
    provider_id: str | None,
    state: str | None,
    county: str | None,
) -> dict[str, Any]:
    st = (state or "").upper()
    co = (county or "").lower()
    provider = provider_id or ""

    best = None
    for row in OFFICES:
        if row["provider_id"] != provider:
            continue
        if row["state"] and row["state"] != st:
            continue
        ckey = row.get("county") or ""
        if ckey and ckey not in co:
            continue
        best = row
        if ckey:
            break

    if best is None and provider == "blm_lpad":
        url, phone = BLM_STATE_OFFICES.get(st, ("https://www.blm.gov/programs/lands-and-realty/land-tenure", "202-208-3801"))
        best = {
            "provider_id": "blm_lpad",
            "state": st,
            "county": co,
            "source_name": f"BLM LPAD · {st or 'US'}",
            "office": f"BLM {st} State Office" if st else "BLM Lands & Realty",
            "website": url,
            "phone": phone,
            "parcel_lookup": "https://www.blm.gov/services/land-records",
            "how": "Federal disposal tract — field office confirms if/when it can be sold or exchanged.",
        }

    if best is None:
        q = quote_plus(f"{county or ''} {state or ''} property tax sale treasurer assessor".strip())
        best = {
            "provider_id": provider,
            "state": st,
            "county": co,
            "source_name": f"Public land inventory · {county or 'County'}, {st or 'US'}",
            "office": f"{county or 'County'} {st} Treasurer / Assessor".strip(),
            "website": f"https://www.google.com/search?q={q}",
            "phone": None,
            "parcel_lookup": f"https://www.google.com/search?q={quote_plus((county or '') + ' ' + (st or '') + ' parcel viewer assessor')}",
            "how": "Public GIS inventory — confirm sale status with the county Treasurer or Assessor.",
        }
    return best


def build_sourcing_bundle(
    *,
    provider_id: str | None,
    source_url: str | None,
    title: str,
    apn: str | None,
    state: str | None,
    county: str | None,
    latitude: float | None,
    longitude: float | None,
    raw: dict | None = None,
) -> dict[str, Any]:
    """Actionable links + office card for every parcel."""
    office = resolve_office(provider_id=provider_id, state=state, county=county)
    raw = raw or {}
    links: list[dict[str, Any]] = []

    # 1) Direct posting / source record
    posting = source_url or office.get("website")
    if posting:
        links.append(
            {
                "label": "Open source posting",
                "url": posting,
                "kind": "primary",
            }
        )

    # 2) Parcel lookup (assessor / PIN)
    lookup = office.get("parcel_lookup")
    if apn and lookup:
        # Prefer searchable assessor when we have APN
        if "google.com/search" in lookup:
            lookup = f"https://www.google.com/search?q={quote_plus(str(apn) + ' ' + (county or '') + ' ' + (state or '') + ' parcel')}"
        links.append({"label": f"Parcel lookup · {apn}", "url": lookup, "kind": "lookup"})
    elif lookup:
        links.append({"label": "Parcel / assessor lookup", "url": lookup, "kind": "lookup"})

    # 3) Contact office
    contact_url = office.get("website") or f"https://www.google.com/search?q={quote_plus(office.get('office') or title)}"
    phone = office.get("phone")
    links.append(
        {
            "label": f"Call {phone}" if phone else f"Contact {office.get('office')}",
            "url": f"tel:{phone.replace('-', '')}" if phone else contact_url,
            "kind": "contact",
            "phone": phone,
        }
    )
    if phone:
        links.append(
            {
                "label": "Office website",
                "url": contact_url,
                "kind": "contact_web",
            }
        )

    # 4) Map
    if latitude is not None and longitude is not None:
        links.append(
            {
                "label": "Map pin",
                "url": f"https://www.google.com/maps?q={latitude},{longitude}",
                "kind": "map",
            }
        )

    # Dedupe by URL, keep order, allow up to 5
    seen: set[str] = set()
    out_links = []
    for link in links:
        u = link["url"]
        if u in seen:
            continue
        seen.add(u)
        out_links.append(link)

    return {
        "source_name": office.get("source_name"),
        "office": office.get("office"),
        "website": office.get("website"),
        "phone": phone,
        "how_to_buy": office.get("how"),
        "provider_id": provider_id,
        "links": out_links[:5],
    }
