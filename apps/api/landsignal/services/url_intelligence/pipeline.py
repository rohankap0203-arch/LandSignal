"""Universal Listing URL Intelligence pipeline.

URL → Acquisition → Extraction → Identity → Canonical model → Enrichment
→ Validation/Confidence → Existing analyze_parcel → Standard report.
"""

from __future__ import annotations

import time
from typing import Any
from uuid import UUID

import httpx
import structlog

from landsignal.services.url_intelligence.adapters import select_adapter
from landsignal.services.url_intelligence.adapters.generic import host_label
from landsignal.services.url_intelligence.confidence import compute_url_confidence
from landsignal.services.url_intelligence.conflicts import detect_acreage_conflict
from landsignal.services.url_intelligence.identity import (
    apply_user_corrections,
    find_duplicate_parcel,
    resolve_identity,
)
from landsignal.services.url_intelligence.provenance import draft_from_fields, unwrap
from landsignal.services.url_intelligence.semantic import semantic_extract
from landsignal.services.url_intelligence.ssrf import validate_listing_url

log = structlog.get_logger()

STAGE_DEFS = [
    ("reading_listing", "Reading listing"),
    ("identifying_property", "Identifying property"),
    ("resolving_parcel", "Resolving parcel"),
    ("verifying_property_data", "Verifying property data"),
    ("enriching_location", "Enriching location intelligence"),
    ("evaluating_market", "Evaluating market conditions"),
    ("modeling_value", "Modeling land value"),
    ("evaluating_risk", "Evaluating risk"),
    ("calculating_opportunity", "Calculating opportunity score"),
    ("building_report", "Building intelligence report"),
]


def _stage(id_: str, status: str = "pending", detail: str | None = None, ms: int | None = None) -> dict[str, Any]:
    label = next((l for i, l in STAGE_DEFS if i == id_), id_)
    out: dict[str, Any] = {"id": id_, "label": label, "status": status}
    if detail:
        out["detail"] = detail
    if ms is not None:
        out["ms"] = ms
    return out


def _facts_from_draft(draft: dict[str, Any], identity: dict[str, Any] | None = None) -> list[str]:
    facts: list[str] = []
    if draft.get("acreage") is not None:
        try:
            facts.append(f"{float(draft['acreage']):g} acres detected")
        except (TypeError, ValueError):
            pass
    if draft.get("county") and draft.get("state"):
        facts.append(f"{draft['county']}, {draft['state']}")
    elif draft.get("state"):
        facts.append(f"State: {draft['state']}")
    if draft.get("asking_price_usd") is not None:
        try:
            facts.append(f"Asking price: ${float(draft['asking_price_usd']):,.0f}")
        except (TypeError, ValueError):
            pass
    if draft.get("apn"):
        facts.append(f"APN: {draft['apn']}")
    if identity and identity.get("state") in {"VERIFIED", "HIGH_CONFIDENCE", "PROBABLE"}:
        facts.append("Parcel identified")
    if draft.get("zoning"):
        facts.append("Zoning data located")
    if draft.get("latitude") is not None and draft.get("longitude") is not None:
        facts.append("Coordinates resolved")
    return facts[:8]


def missing_required(draft: dict[str, Any]) -> list[str]:
    need = []
    if not draft.get("title"):
        need.append("title")
    if not draft.get("state") or len(str(draft.get("state"))) != 2:
        need.append("state")
    if draft.get("acreage") is None:
        need.append("acreage")
    if draft.get("latitude") is None or draft.get("longitude") is None:
        need.append("coordinates")
    return need


def material_missing(draft: dict[str, Any]) -> list[dict[str, str]]:
    """Only fields that truly block running the intelligence engine.

    Acreage is preferred but no longer blocking — many listing URLs omit it and
    the scoring engine already handles unknown acreage. Coordinates are only
    blocking when we could not geocode any location signal from the URL.
    """
    out = []
    if not draft.get("state") or len(str(draft.get("state") or "")) != 2:
        # State can be skipped if we already resolved coordinates
        if draft.get("latitude") is None or draft.get("longitude") is None:
            out.append(
                {
                    "field": "state",
                    "label": "state",
                    "prompt": "We need a 2-letter state (or coordinates) to place this property.",
                    "unit": "",
                }
            )
    if draft.get("latitude") is None or draft.get("longitude") is None:
        out.append(
            {
                "field": "coordinates",
                "label": "coordinates",
                "prompt": "Add map coordinates (lat, lon) — or a city/county/state we can geocode.",
                "unit": "lat,lon",
            }
        )
    return out


async def geocode_address(address: str, state: str | None = None) -> dict[str, float] | None:
    q = address if not state else f"{address}, {state}, USA"
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": q, "format": "json", "limit": 1, "countrycodes": "us"},
                headers={"User-Agent": "LandSignal/1.0 (user-submitted listing analyze)"},
            )
            if resp.status_code >= 400:
                return None
            data = resp.json()
            if not data:
                return None
            return {"latitude": float(data[0]["lat"]), "longitude": float(data[0]["lon"])}
    except Exception as exc:  # noqa: BLE001
        log.info("geocode_failed", error=str(exc)[:160])
        return None


async def resolve_coordinates(draft: dict[str, Any]) -> tuple[dict[str, float] | None, str | None]:
    """Try multiple geocode strategies from anything found in the URL/draft."""
    if draft.get("latitude") is not None and draft.get("longitude") is not None:
        try:
            return (
                {"latitude": float(draft["latitude"]), "longitude": float(draft["longitude"])},
                "listing_or_url",
            )
        except (TypeError, ValueError):
            pass

    state = draft.get("state")
    queries: list[tuple[str, str]] = []
    if draft.get("address"):
        queries.append((str(draft["address"]), "address"))
    if draft.get("geocode_query"):
        queries.append((str(draft["geocode_query"]), "geocode_query"))
    if draft.get("city") and state:
        queries.append((f"{draft['city']}, {state}", "city_state"))
    if draft.get("county") and state:
        queries.append((f"{draft['county']} County, {state}", "county_state"))
    if draft.get("zip"):
        queries.append((str(draft["zip"]), "zip"))
    if state and not queries:
        # Last-resort: state centroid — better than blocking the user
        queries.append((f"{state}, USA", "state"))

    seen: set[str] = set()
    for q, method in queries:
        key = q.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        # If query already includes state, don't double-append
        geo = await geocode_address(q, None if (state and state in q) or method == "state" else state)
        if geo:
            return geo, method
    return None, None


async def _fetch_html(url: str) -> tuple[str, str, str | None]:
    """Returns html, fetch_status, final_url."""
    headers = {
        # Browser-like UA — marketplace CDNs often hard-block obvious bots.
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
    }
    fetch_status = "ok"
    html = ""
    final_url = url
    try:
        async with httpx.AsyncClient(
            timeout=18.0,
            follow_redirects=True,
            max_redirects=5,
        ) as client:
            resp = await client.get(url, headers=headers)
            final_url = str(resp.url)
            ctype = (resp.headers.get("content-type") or "").lower()
            if "text/html" not in ctype and "application/xhtml" not in ctype and ctype and "text/" not in ctype:
                return "", "unsupported_mime", final_url
            body = resp.content[: 2_500_000]
            html = body.decode(resp.encoding or "utf-8", errors="replace")
            low = html.lower()
            if resp.status_code in (401, 403, 429) or "access denied" in low[:2000] or "akamai" in low[:1500] and "denied" in low[:2000]:
                fetch_status = "blocked"
            elif resp.status_code >= 400:
                fetch_status = "http_error"
            elif len(html) < 800 or ("__NEXT_DATA__" in html and "og:title" not in low):
                if "og:title" not in low and "application/ld+json" not in low:
                    fetch_status = "thin_or_app_shell"
    except Exception as exc:  # noqa: BLE001
        log.info("listing_url_fetch_failed", url=url[:180], error=str(exc)[:200])
        return "", "network_error", url
    return html, fetch_status, final_url


def _fallback_payload(url: str, domain: str | None, fetch_status: str) -> dict[str, Any]:
    return {
        "message": "We couldn't read enough information from this listing automatically.",
        "options": [
            {"id": "paste_details", "label": "Paste listing details", "href": "/ingest"},
            {"id": "enter_address", "label": "Enter address / APN", "href": "/ingest"},
            {"id": "manual_import", "label": "Manual import", "href": "/ingest"},
        ],
        "fetch_status": fetch_status,
        "source_domain": domain,
        "source_url": url,
    }


async def extract_listing_intelligence(url: str) -> dict[str, Any]:
    """Stages A–C + semantic + identity preview (no parcel write)."""
    stages: list[dict[str, Any]] = [_stage(i, "pending") for i, _ in STAGE_DEFS]
    t0 = time.perf_counter()

    v = validate_listing_url(url)
    if not v["ok"]:
        stages[0] = _stage("reading_listing", "error", v["error"])
        return {
            "ok": False,
            "error": v["error"],
            "stages": stages,
            "facts": [],
            "draft": {"source_url": url},
            "fields": {},
            "missing": ["title", "state", "acreage", "coordinates"],
            "missing_material": material_missing({"source_url": url}),
            "fetch_status": "invalid_url",
            "fallback": _fallback_payload(url, None, "invalid_url"),
            "needs_confirmation": True,
        }

    canonical = v["canonical_url"]
    domain = v["domain"]
    stages[0] = _stage("reading_listing", "running")

    html, fetch_status, final_url = await _fetch_html(canonical)
    # Re-validate redirect target
    if final_url and final_url != canonical:
        v2 = validate_listing_url(final_url)
        if not v2["ok"]:
            stages[0] = _stage("reading_listing", "error", "Redirect target blocked")
            return {
                "ok": False,
                "error": "We couldn't read enough information from this listing automatically.",
                "stages": stages,
                "facts": [],
                "draft": {"source_url": url, "source_host": host_label(url)},
                "fields": {},
                "missing": ["title", "state", "acreage", "coordinates"],
                "missing_material": material_missing({"source_url": url}),
                "fetch_status": "blocked",
                "fallback": _fallback_payload(url, domain, "blocked"),
                "needs_confirmation": True,
            }
        canonical = v2["canonical_url"]
        domain = v2["domain"]

    ms_read = int((time.perf_counter() - t0) * 1000)
    adapter = select_adapter(canonical, domain or "")
    # Always run extract — URL slug hints work even when HTML is empty/blocked
    raw = adapter.extract(html or "", url=canonical, domain=domain or "")
    if not raw.get("source_url"):
        raw["source_url"] = canonical
    if not raw.get("source_host"):
        raw["source_host"] = host_label(canonical)
    raw["adapter_id"] = getattr(adapter, "id", "generic")
    fields = adapter.normalize(raw, url=canonical, domain=domain or "")
    stages[0] = _stage("reading_listing", "done", f"via {getattr(adapter, 'name', 'adapter')}", ms_read)

    t1 = time.perf_counter()
    stages[1] = _stage("identifying_property", "running")
    semantic = semantic_extract(raw.get("description") or unwrap(fields.get("description")), source_url=canonical)
    for nest_key in ("utilities", "access", "environment", "hazards", "restrictions"):
        if nest_key in semantic:
            fields[nest_key] = semantic[nest_key]

    draft = draft_from_fields(fields)
    draft["source_url"] = canonical
    draft["source_host"] = host_label(canonical)
    draft["provider_id"] = "listing_url"
    draft["external_id"] = f"url:{domain}:{hash(canonical) & 0xFFFFFFFF:x}"
    # Carry through URL-hint extras not in provenanced field map
    for k in ("city", "zip", "geocode_query", "county", "apn", "acreage", "asking_price_usd", "address", "state", "title"):
        if raw.get(k) is not None and draft.get(k) in (None, ""):
            draft[k] = raw[k]
    if raw.get("zoning"):
        draft["zoning"] = raw["zoning"]
    if not draft.get("title"):
        bits = []
        if draft.get("acreage") is not None:
            bits.append(f"{float(draft['acreage']):g}-acre")
        bits.append("listing")
        place = draft.get("county") or draft.get("city") or draft.get("state") or host_label(canonical)
        draft["title"] = f"{' '.join(bits)} in {place}".replace("  ", " ").title()

    geo, geo_method = await resolve_coordinates(draft)
    if geo:
        draft["latitude"] = geo["latitude"]
        draft["longitude"] = geo["longitude"]
        from landsignal.services.url_intelligence.provenance import provenanced

        conf_map = {
            "listing_or_url": 0.9,
            "address": 0.75,
            "geocode_query": 0.7,
            "city_state": 0.65,
            "county_state": 0.55,
            "zip": 0.6,
            "state": 0.35,
        }
        gconf = conf_map.get(geo_method or "", 0.5)
        fields["latitude"] = provenanced(
            geo["latitude"],
            source="geospatial_calculation",
            confidence=gconf,
            extraction_method=f"nominatim_{geo_method or 'geocode'}",
            source_url=canonical,
        )
        fields["longitude"] = provenanced(
            geo["longitude"],
            source="geospatial_calculation",
            confidence=gconf,
            extraction_method=f"nominatim_{geo_method or 'geocode'}",
            source_url=canonical,
        )
        if geo_method and geo_method != "listing_or_url":
            draft.setdefault("_coordinate_source", geo_method)

    stages[1] = _stage("identifying_property", "done", ms=int((time.perf_counter() - t1) * 1000))

    t2 = time.perf_counter()
    stages[2] = _stage("resolving_parcel", "running")
    identity = resolve_identity(fields, draft)
    stages[2] = _stage(
        "resolving_parcel",
        "done",
        f"{identity['state']} ({identity['propertyIdentityConfidence']})",
        int((time.perf_counter() - t2) * 1000),
    )

    t3 = time.perf_counter()
    stages[3] = _stage("verifying_property_data", "running")
    conflicts: list[dict[str, Any]] = []
    # Internal consistency: price/acre vs acreage*ppa if both exist — skip if N/A
    miss = missing_required(draft)
    material = material_missing(draft)
    conf = compute_url_confidence(
        fields=fields,
        identity=identity,
        conflicts=conflicts,
        fetch_status=fetch_status,
        semantic=semantic,
    )
    stages[3] = _stage("verifying_property_data", "done", ms=int((time.perf_counter() - t3) * 1000))

    # Remaining stages pending until confirm/analyze
    for i in range(4, len(stages)):
        stages[i] = _stage(STAGE_DEFS[i][0], "pending")

    thin = fetch_status in {"blocked", "thin_or_app_shell", "http_error", "network_error", "unsupported_mime"}
    note = None
    if thin and not miss:
        note = (
            f"{draft.get('source_host') or 'This site'} blocked a full page read, but we recovered "
            "enough from the listing URL to run intelligence. Review once, then continue."
        )
    elif thin:
        note = (
            f"{draft.get('source_host') or 'This site'} often blocks automated page reads. "
            "We pulled what we could from the URL — confirm the fields below and LandSignal "
            "will still run the full intelligence stack."
        )
    elif miss:
        note = "We pulled a draft from the page. Confirm the fields below, then run intelligence."
    else:
        note = "Draft looks complete. Review once, then run intelligence."

    facts = _facts_from_draft(draft, identity)
    ok = True
    error = None
    # Only hard-fail when we have essentially nothing usable
    if fetch_status == "network_error" and len(miss) >= 3 and not draft.get("acreage") and not draft.get("state"):
        ok = False
        error = "We couldn't read enough information from this listing automatically."

    return {
        "ok": ok,
        "error": error,
        "draft": draft,
        "fields": fields,
        "semantic": semantic,
        "identity": identity,
        "conflicts": conflicts,
        "confidence": conf,
        "missing": miss,
        "missing_material": material,
        "needs_confirmation": bool(material),
        "fetch_status": fetch_status,
        "note": note,
        "source_host": draft.get("source_host"),
        "source_domain": domain,
        "canonical_url": canonical,
        "adapter_id": getattr(adapter, "id", "generic"),
        "stages": stages,
        "facts": facts,
        "fallback": _fallback_payload(canonical, domain, fetch_status)
        if (not ok or (thin and len(miss) >= 3 and not draft.get("acreage") and not draft.get("state")))
        else None,
        "imported_listing": {
            "label": "Imported Listing",
            "domain": domain,
            "source_url": canonical,
            "view_original": canonical,
        },
    }


async def analyze_listing_url(
    store: Any,
    url: str,
    *,
    corrections: dict[str, Any] | None = None,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Full pathway: extract → resolve → upsert/reuse → analyze_parcel → report hooks."""
    from landsignal.services.alerts import evaluate_rules
    from landsignal.services.analyze import analyze_parcel
    from landsignal.services.land_alerts import match_parcel
    from landsignal.settings import get_settings

    extracted = await extract_listing_intelligence(url)
    stages = list(extracted.get("stages") or [])
    draft = apply_user_corrections(extracted.get("draft") or {}, corrections)
    # Mark user-confirmed fields in provenance
    fields = dict(extracted.get("fields") or {})
    for fname in draft.get("_user_confirmed_fields") or []:
        key = {
            "asking_price_usd": "askingPrice",
            "acreage": "acreage",
            "state": "state",
            "county": "county",
            "apn": "apn",
            "address": "address",
            "latitude": "latitude",
            "longitude": "longitude",
            "title": "title",
            "description": "description",
        }.get(fname, fname)
        if key in fields and isinstance(fields[key], dict):
            fields[key] = {
                **fields[key],
                "value": draft.get(fname),
                "source": "USER_CONFIRMED",
                "confidence": 1.0,
                "knowledgeState": "CONFIRMED",
            }
        elif fname in ("latitude", "longitude") and draft.get(fname) is not None:
            from landsignal.services.url_intelligence.provenance import provenanced

            fields[key] = provenanced(
                draft[fname],
                source="USER_CONFIRMED",
                confidence=1.0,
                extraction_method="user_correction",
                source_url=draft.get("source_url"),
            )

    # Apply coordinate pair correction
    if corrections and corrections.get("latitude") is not None and corrections.get("longitude") is not None:
        try:
            draft["latitude"] = float(corrections["latitude"])
            draft["longitude"] = float(corrections["longitude"])
        except (TypeError, ValueError):
            pass
    if corrections and "coordinates" in corrections:
        # "lat,lon" string
        raw_c = str(corrections["coordinates"])
        if "," in raw_c:
            a, b = raw_c.split(",", 1)
            try:
                draft["latitude"] = float(a.strip())
                draft["longitude"] = float(b.strip())
            except ValueError:
                pass

    identity = resolve_identity(fields, draft)
    extracted["identity"] = identity
    extracted["draft"] = draft
    extracted["fields"] = fields
    extracted["missing"] = missing_required(draft)
    extracted["missing_material"] = material_missing(draft)
    extracted["facts"] = _facts_from_draft(draft, identity)
    extracted["needs_confirmation"] = bool(extracted["missing_material"])

    if extracted["needs_confirmation"] and not corrections:
        # Stop before write — ask for material fields
        return {
            **extracted,
            "parcel_id": None,
            "duplicate": find_duplicate_parcel(store, draft),
            "status": "needs_confirmation",
        }

    # If still missing after corrections, keep asking
    if extracted["missing_material"]:
        return {
            **extracted,
            "parcel_id": None,
            "duplicate": find_duplicate_parcel(store, draft),
            "status": "needs_confirmation",
            "note": "A few critical fields are still needed before we can run the full report.",
        }

    duplicate = find_duplicate_parcel(store, draft)
    settings = get_settings()

    def _mark(idx: int, status: str, detail: str | None = None, ms: int | None = None):
        sid = STAGE_DEFS[idx][0]
        stages[idx] = _stage(sid, status, detail, ms)

    # Enrichment + scoring via existing engine
    t4 = time.perf_counter()
    _mark(4, "running")

    parcel_id: UUID | None = None
    listing = None
    if duplicate and not force_refresh:
        parcel_id = UUID(duplicate["parcel_id"])
        parcel = store.parcels.get(parcel_id)
        listing = store.listing_for_parcel(parcel_id)
        # Refresh listing fields from new draft
        if listing and parcel:
            if draft.get("asking_price_usd") is not None:
                listing.asking_price_usd = draft["asking_price_usd"]
                if draft.get("acreage"):
                    listing.price_per_acre_usd = draft["asking_price_usd"] / draft["acreage"]
            if draft.get("title"):
                listing.title = draft["title"]
            if draft.get("description"):
                listing.description = draft["description"]
            if draft.get("source_url"):
                listing.source_url = draft["source_url"]
            listing.raw = {
                **(listing.raw or {}),
                "url_intelligence": {
                    "fields": fields,
                    "identity": identity,
                    "confidence": extracted.get("confidence"),
                    "imported_listing": extracted.get("imported_listing"),
                    "semantic": extracted.get("semantic"),
                },
            }
            store.listings[listing.id] = listing
            if draft.get("acreage") is not None and parcel.acreage is not None:
                conflict = detect_acreage_conflict(draft["acreage"], parcel.acreage)
                if conflict:
                    extracted.setdefault("conflicts", []).append(conflict)
    else:
        payload = {
            "title": draft.get("title") or f"Listing from {draft.get('source_host') or 'URL'}",
            "state": str(draft.get("state") or "").upper()[:2],
            "county": draft.get("county"),
            "apn": draft.get("apn"),
            "address": draft.get("address"),
            "acreage": draft.get("acreage"),
            "asking_price_usd": draft.get("asking_price_usd"),
            "latitude": draft.get("latitude"),
            "longitude": draft.get("longitude"),
            "description": draft.get("description"),
            "source_url": draft.get("source_url") or url,
            "provider_id": "listing_url",
            "external_id": draft.get("external_id"),
        }
        # Attach intelligence envelope in raw via upsert
        payload["_url_intelligence"] = {
            "fields": fields,
            "identity": identity,
            "confidence": extracted.get("confidence"),
            "imported_listing": extracted.get("imported_listing"),
            "semantic": extracted.get("semantic"),
            "conflicts": extracted.get("conflicts"),
            "adapter_id": extracted.get("adapter_id"),
            "canonical_url": extracted.get("canonical_url"),
        }
        parcel, listing = store.upsert_manual(payload)
        # Stash intelligence on listing.raw cleanly
        listing.raw = {
            **{k: v for k, v in payload.items() if k not in ("polygon", "_url_intelligence")},
            "url_intelligence": payload["_url_intelligence"],
        }
        store.listings[listing.id] = listing
        parcel_id = parcel.id

        if draft.get("acreage") is not None and parcel.acreage is not None:
            # same source — no conflict yet; enrichment may add later
            pass

    _mark(4, "done", ms=int((time.perf_counter() - t4) * 1000))
    _mark(5, "running")
    t5 = time.perf_counter()

    assert parcel_id is not None
    score = await analyze_parcel(store, parcel_id, fast=False)
    _mark(5, "done", ms=int((time.perf_counter() - t5) * 1000))
    _mark(6, "done", "Value model from Land Signal engine")
    _mark(7, "done", f"Risk {score.risk:.0f}")
    _mark(8, "done", f"Opportunity {score.opportunity:.0f}")
    _mark(9, "done", "Standard intelligence report ready")

    alerts = evaluate_rules(store, score, settings)
    land_matches = match_parcel(
        store, parcel_id, origin="new_discovery", update_kind="new_listing", settings=settings
    )

    # Refresh confidence with enrichment present
    enrichment = store.enrichments.get(parcel_id)
    extracted["confidence"] = compute_url_confidence(
        fields=fields,
        identity=identity,
        conflicts=extracted.get("conflicts") or [],
        fetch_status=extracted.get("fetch_status") or "ok",
        semantic=extracted.get("semantic") or {},
        enrichment_present=bool(enrichment),
    )

    # Cache ingest record on store if supported
    cache = getattr(store, "url_ingest_cache", None)
    if cache is not None:
        cache[extracted.get("canonical_url") or url] = {
            "parcel_id": str(parcel_id),
            "retrieved_at": time.time(),
            "identity": identity,
            "confidence": extracted["confidence"],
        }

    return {
        **extracted,
        "ok": True,
        "error": None,
        "stages": stages,
        "parcel_id": str(parcel_id),
        "listing_id": str(listing.id) if listing else None,
        "score_id": str(score.id),
        "duplicate": duplicate,
        "status": "complete",
        "alerts_triggered": len(alerts),
        "land_alert_matches": len(land_matches),
        "needs_confirmation": False,
        "fallback": None,
        "report_path": f"/parcels/{parcel_id}",
    }
