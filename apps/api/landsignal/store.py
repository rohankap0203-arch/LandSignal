from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from landsignal.models import (
    AlertRecord,
    AlertRuleRecord,
    EnrichmentBundle,
    InvestorProfileUpdate,
    LandAlertMatch,
    LandAlertProfile,
    ListingRecord,
    ParcelRecord,
    Provenanced,
    KnowledgeState,
    ScoreRecord,
)
from landsignal.scoring.geospatial import acres_from_square_meters, ring_area_square_meters


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MemoryStore:
    """Phase 1 store. Swap for Postgres/PostGIS without changing routers."""

    def __init__(self) -> None:
        self.parcels: dict[UUID, ParcelRecord] = {}
        self.listings: dict[UUID, ListingRecord] = {}
        self.enrichments: dict[UUID, EnrichmentBundle] = {}
        self.scores: dict[UUID, list[ScoreRecord]] = {}
        self.alerts: list[AlertRecord] = []
        self.alert_rules: dict[UUID, AlertRuleRecord] = {}
        self.land_alert_profiles: dict[UUID, LandAlertProfile] = {}
        self.land_alert_matches: dict[str, LandAlertMatch] = {}
        self.watchlists: dict[UUID, set[UUID]] = {}
        self.investor_profile: dict[str, Any] = {
            "capital_available_usd": 1_000_000,
            "min_acres": 20,
            "max_price_usd": 750_000,
            "target_hold_years_min": 5,
            "target_hold_years_max": 15,
            "min_target_irr": 0.12,
            "preferred_strategies": ["FARMLAND", "LAND_BANK", "DEVELOPMENT"],
            "risk_tolerance": "MODERATE",
            "notify_email": "",
            "watchlist_email_updates": True,
        }
        self.dd_items: dict[UUID, list[dict[str, Any]]] = {}
        # parcel_id -> snapshot of key metrics for change detection
        self.watch_snapshots: dict[UUID, dict[str, Any]] = {}
        # O(1) parcel → listing lookup (kept in sync on upsert / restore)
        self._listing_id_by_parcel: dict[UUID, UUID] = {}
        # O(1) (provider_id, external_id) → listing — required for 100k+ discovers
        self._listing_id_by_external: dict[tuple[str, str], UUID] = {}

    def seed_demo(self) -> None:
        """Deterministic DEMO fixtures for UI walkthrough — never labeled as live feeds."""
        demos = [
            {
                "title": "DEMO — Madison County Tillable Tract",
                "state": "IA",
                "county": "Madison",
                "apn": "DEMO-IA-001",
                "acreage": 78.4,
                "asking_price_usd": 475000,
                "lat": 41.3342,
                "lon": -94.0155,
                "dom": 38,
                "price_reduction_pct": 12,
                "fixture_enrichment": {
                    "prime_farmland_pct": 74,
                    "wetland_pct": 6,
                    "flood_zone_pct": 4,
                    "avg_slope_pct": 2.5,
                    "max_slope_pct": 7,
                    "elevation_m": 340,
                    "legal_access_confidence": 82,
                },
            },
            {
                "title": "DEMO — Growth-Corridor Acreage",
                "state": "TX",
                "county": "Williamson",
                "apn": "DEMO-TX-014",
                "acreage": 42.0,
                "asking_price_usd": 620000,
                "lat": 30.633,
                "lon": -97.678,
                "dom": 21,
                "price_reduction_pct": 0,
                "fixture_enrichment": {
                    "prime_farmland_pct": 28,
                    "wetland_pct": 3,
                    "flood_zone_pct": 8,
                    "avg_slope_pct": 4,
                    "max_slope_pct": 11,
                    "elevation_m": 250,
                    "legal_access_confidence": 75,
                    "path_of_growth_score": 84,
                    "zoning_development_friendly": 72,
                },
            },
            {
                "title": "DEMO — High-Wetland Recreational",
                "state": "MN",
                "county": "Aitkin",
                "apn": "DEMO-MN-077",
                "acreage": 120.0,
                "asking_price_usd": 390000,
                "lat": 46.533,
                "lon": -93.710,
                "dom": 160,
                "price_reduction_pct": 8,
                "fixture_enrichment": {
                    "prime_farmland_pct": 12,
                    "wetland_pct": 48,
                    "flood_zone_pct": 22,
                    "avg_slope_pct": 3,
                    "max_slope_pct": 9,
                    "elevation_m": 375,
                    "legal_access_confidence": 55,
                },
            },
        ]
        for d in demos:
            poly = _square_polygon(d["lon"], d["lat"], d["acreage"])
            parcel = ParcelRecord(
                parcel_id=d["apn"],
                apn=d["apn"],
                address=f"{d['county']} County, {d['state']}",
                county=d["county"],
                state=d["state"],
                latitude=d["lat"],
                longitude=d["lon"],
                polygon=poly,
                acreage=d["acreage"],
                geometry_confidence=70,
                is_demo=True,
            )
            listing = ListingRecord(
                parcel_id=parcel.id,
                provider_id="demo",
                external_id=d["apn"],
                asking_price_usd=d["asking_price_usd"],
                price_per_acre_usd=d["asking_price_usd"] / d["acreage"],
                listed_at=_utcnow() - timedelta(days=d["dom"]),
                last_seen_at=_utcnow(),
                days_on_market=d["dom"],
                title=d["title"],
                description="DEMO FIXTURE — not a live market listing.",
                is_demo=True,
                raw={"price_reduction_pct": d["price_reduction_pct"], "fixture": True},
            )
            self.parcels[parcel.id] = parcel
            self.listings[listing.id] = listing
            self.index_listing(listing)
            fe = d["fixture_enrichment"]
            self.enrichments[parcel.id] = EnrichmentBundle(
                soil=Provenanced(
                    value={"prime_farmland_pct": fe["prime_farmland_pct"]},
                    knowledge_state=KnowledgeState.ESTIMATED,
                    source="demo_fixture",
                    confidence=60,
                    retrieved_at=_utcnow(),
                    normalized=fe,
                    geographic_resolution="fixture",
                ),
                flood=Provenanced(
                    value={"flood_zone_pct": fe["flood_zone_pct"]},
                    knowledge_state=KnowledgeState.ESTIMATED,
                    source="demo_fixture",
                    confidence=60,
                    retrieved_at=_utcnow(),
                    normalized={"flood_zone_pct": fe["flood_zone_pct"]},
                ),
                wetlands=Provenanced(
                    value={"wetland_pct": fe["wetland_pct"]},
                    knowledge_state=KnowledgeState.ESTIMATED,
                    source="demo_fixture",
                    confidence=60,
                    retrieved_at=_utcnow(),
                    normalized={"wetland_pct": fe["wetland_pct"]},
                ),
                terrain=Provenanced(
                    value={
                        "elevation_m": fe["elevation_m"],
                        "avg_slope_pct": fe["avg_slope_pct"],
                        "max_slope_pct": fe["max_slope_pct"],
                    },
                    knowledge_state=KnowledgeState.ESTIMATED,
                    source="demo_fixture",
                    confidence=60,
                    retrieved_at=_utcnow(),
                    normalized=fe,
                ),
                access=Provenanced(
                    value={"legal_access_confidence": fe["legal_access_confidence"]},
                    knowledge_state=KnowledgeState.ESTIMATED,
                    source="demo_fixture",
                    confidence=40,
                    retrieved_at=_utcnow(),
                    normalized={
                        "legal_access_confidence": fe["legal_access_confidence"],
                        "note": "Not legally verified",
                    },
                ),
                comps=Provenanced(
                    value={"comps_count": 3, "estimated_value_base_usd": d["asking_price_usd"] * 1.22},
                    knowledge_state=KnowledgeState.ESTIMATED,
                    source="demo_fixture",
                    confidence=45,
                    retrieved_at=_utcnow(),
                    normalized={
                        "comps_count": 3,
                        "estimated_value_low_usd": d["asking_price_usd"] * 1.05,
                        "estimated_value_base_usd": d["asking_price_usd"] * 1.22,
                        "estimated_value_high_usd": d["asking_price_usd"] * 1.45,
                        "downside_value_usd": d["asking_price_usd"] * 0.85,
                        "development_upside_usd": d["asking_price_usd"] * 2.1,
                        "path_of_growth_score": fe.get("path_of_growth_score", 55),
                        "zoning_development_friendly": fe.get("zoning_development_friendly", 45),
                        "liquidity_score": 52,
                        "scarcity_score": 58,
                        "catalyst_score": 35,
                        "seller_pressure_score": 60 if d["dom"] > 100 else 48,
                        "solar_irradiance_score": 65,
                        "timber_suitability": 30,
                    },
                ),
            )
            self.dd_items[parcel.id] = default_dd_checklist()

    def upsert_manual(self, payload: dict[str, Any]) -> tuple[ParcelRecord, ListingRecord]:
        poly = payload.get("polygon")
        acreage = payload.get("acreage")
        if acreage is None and poly:
            acreage = acres_from_square_meters(ring_area_square_meters(poly[0]))
        geom_conf = 80.0 if poly else (50.0 if payload.get("latitude") else 20.0)
        is_demo = bool(payload.get("is_demo", False))
        parcel = ParcelRecord(
            parcel_id=payload.get("apn"),
            apn=payload.get("apn"),
            address=payload.get("address"),
            county=payload.get("county"),
            state=payload.get("state"),
            latitude=payload.get("latitude"),
            longitude=payload.get("longitude"),
            polygon=poly,
            acreage=acreage,
            geometry_confidence=geom_conf if poly else (55.0 if payload.get("latitude") else 20.0),
            is_demo=is_demo,
        )
        ask = payload.get("asking_price_usd")
        from landsignal.services.memory_guard import slim_listing_raw

        # Never stash full GIS attribute dumps — that alone OOMs ~15Gi VMs at 50k+.
        raw_in = payload.get("raw") if isinstance(payload.get("raw"), dict) else payload
        listing = ListingRecord(
            parcel_id=parcel.id,
            provider_id=payload.get("provider_id") or "manual",
            external_id=payload.get("external_id") or str(uuid4()),
            asking_price_usd=ask,
            price_per_acre_usd=(ask / acreage) if ask and acreage else None,
            listed_at=_utcnow(),
            last_seen_at=_utcnow(),
            days_on_market=payload.get("days_on_market") or 0,
            title=payload.get("title"),
            description=payload.get("description"),
            source_url=payload.get("source_url"),
            raw=slim_listing_raw(raw_in if isinstance(raw_in, dict) else {}),
            is_demo=is_demo,
        )
        self.parcels[parcel.id] = parcel
        self.listings[listing.id] = listing
        self.index_listing(listing)
        # DD checklist is detail-page only — creating it for every discover
        # ingest multiplies RAM for zero search benefit.
        return parcel, listing

    def import_csv(self, text: str) -> list[tuple[ParcelRecord, ListingRecord]]:
        reader = csv.DictReader(io.StringIO(text))
        out = []
        for row in reader:
            payload = {
                "provider_id": "csv",
                "external_id": row.get("external_id") or row.get("apn") or str(uuid4()),
                "title": row.get("title") or row.get("address") or "CSV Parcel",
                "state": (row.get("state") or "").upper()[:2],
                "county": row.get("county"),
                "apn": row.get("apn"),
                "address": row.get("address"),
                "acreage": float(row["acreage"]) if row.get("acreage") else None,
                "asking_price_usd": float(row["asking_price_usd"])
                if row.get("asking_price_usd")
                else None,
                "latitude": float(row["latitude"]) if row.get("latitude") else None,
                "longitude": float(row["longitude"]) if row.get("longitude") else None,
                "source_url": row.get("source_url"),
                "description": row.get("description"),
            }
            out.append(self.upsert_manual(payload))
        return out

    def latest_score(self, parcel_id: UUID) -> ScoreRecord | None:
        items = self.scores.get(parcel_id) or []
        if not items:
            return None
        # Prefer the current algorithm — startup rescore is capped, so older
        # versions can still sit at the end of the list for unscored batches.
        try:
            from landsignal.scoring.engine import ALGORITHM_VERSION

            for s in reversed(items):
                if getattr(s, "algorithm_version", None) == ALGORITHM_VERSION:
                    return s
        except Exception:
            pass
        return items[-1]

    def index_listing(self, listing: ListingRecord) -> None:
        self._listing_id_by_parcel[listing.parcel_id] = listing.id
        if listing.provider_id and listing.external_id:
            self._listing_id_by_external[(listing.provider_id, listing.external_id)] = listing.id

    def rebuild_listing_index(self) -> None:
        self._listing_id_by_parcel = {L.parcel_id: L.id for L in self.listings.values()}
        self._listing_id_by_external = {
            (L.provider_id, L.external_id): L.id
            for L in self.listings.values()
            if L.provider_id and L.external_id
        }

    def listing_by_external(self, provider_id: str | None, external_id: str | None) -> ListingRecord | None:
        if not provider_id or not external_id:
            return None
        lid = self._listing_id_by_external.get((provider_id, external_id))
        if lid is None:
            return None
        return self.listings.get(lid)

    def listing_for_parcel(self, parcel_id: UUID) -> ListingRecord | None:
        lid = self._listing_id_by_parcel.get(parcel_id)
        if lid is not None:
            hit = self.listings.get(lid)
            if hit is not None and hit.parcel_id == parcel_id:
                return hit
        # Fallback + heal index if we ever got out of sync
        for listing in self.listings.values():
            if listing.parcel_id == parcel_id:
                self._listing_id_by_parcel[parcel_id] = listing.id
                return listing
        return None

    def update_profile(self, payload: InvestorProfileUpdate) -> dict[str, Any]:
        data = payload.model_dump()
        prefs = []
        for s in payload.preferred_strategies or []:
            prefs.append(s.value if hasattr(s, "value") else str(s))
        data["preferred_strategies"] = prefs
        self.investor_profile.update(data)
        return self.investor_profile


def default_dd_checklist() -> list[dict[str, Any]]:
    labels = [
        "Confirm title",
        "Order title commitment",
        "Confirm legal access",
        "Survey",
        "Verify easements",
        "Verify zoning directly with county",
        "Confirm water rights",
        "Wetlands delineation if necessary",
        "Environmental assessment if necessary",
        "Soil testing",
        "Utility availability letters",
        "Confirm mineral rights",
        "Review deed restrictions",
    ]
    return [{"label": l, "completed": False, "sort_order": i} for i, l in enumerate(labels)]


def _square_polygon(lon: float, lat: float, acres: float) -> list[list[list[float]]]:
    # Approximate square from acreage
    import math

    m2 = acres * 4046.8564224
    side = math.sqrt(m2)
    m_per_deg_lat = 111_320.0
    m_per_deg_lon = 111_320.0 * math.cos(lat * math.pi / 180)
    d_lat = (side / 2) / m_per_deg_lat
    d_lon = (side / 2) / m_per_deg_lon
    ring = [
        [lon - d_lon, lat - d_lat],
        [lon + d_lon, lat - d_lat],
        [lon + d_lon, lat + d_lat],
        [lon - d_lon, lat + d_lat],
        [lon - d_lon, lat - d_lat],
    ]
    return [ring]


_STORE: MemoryStore | None = None
_PERSIST_PATH = "/tmp/landsignal_inventory.json"


def persist_store(store: MemoryStore | None = None) -> None:
    """Best-effort disk snapshot so API reloads don't wipe live inventory.

    Fat GIS attribute blobs are omitted. Compact real parcel outlines (≤64 verts)
    are kept so View Map can draw the yellow land boundary after restart.
    Fake acreage squares are never persisted.
    """
    import json
    from pathlib import Path

    from landsignal.services.memory_guard import slim_listing_raw, trim_score_lists
    from landsignal.services.parcel_outline import compact_polygon

    store = store or _STORE
    if store is None:
        return
    trim_score_lists(store, keep=1)
    parcels_out = []
    for p in store.parcels.values():
        if p.is_demo:
            continue
        row = p.model_dump(mode="json")
        row["polygon"] = compact_polygon(row.get("polygon"))
        parcels_out.append(row)
    listings_out = []
    for L in store.listings.values():
        if L.is_demo:
            continue
        row = L.model_dump(mode="json")
        row["raw"] = slim_listing_raw(row.get("raw") if isinstance(row.get("raw"), dict) else {})
        # Descriptions already on the listing fields — don't also bloat raw.
        listings_out.append(row)
    scores_out: dict[str, list] = {}
    for pid, scores in store.scores.items():
        if not scores:
            continue
        # Persist latest score only, without giant input snapshots.
        s = scores[-1].model_dump(mode="json")
        s["input_snapshot"] = {}
        s["components"] = (s.get("components") or [])[:8]
        for key in (
            "explanations",
            "why_interesting",
            "why_mispriced",
            "what_could_kill",
            "why_still_available",
            "manual_verification",
        ):
            if isinstance(s.get(key), list):
                s[key] = s[key][:6]
        scores_out[str(pid)] = [s]
    payload = {
        "parcels": parcels_out,
        "listings": listings_out,
        "scores": scores_out,
        "investor_profile": store.investor_profile,
        "land_alert_profiles": [p.model_dump(mode="json") for p in store.land_alert_profiles.values()],
        "land_alert_matches": [m.model_dump(mode="json") for m in store.land_alert_matches.values()],
        "alerts": [a.model_dump(mode="json") for a in store.alerts[:500]],
        "alert_rules": [r.model_dump(mode="json") for r in store.alert_rules.values()],
    }
    Path(_PERSIST_PATH).write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")


def load_persisted_store(store: MemoryStore) -> int:
    import json
    from pathlib import Path

    import structlog

    path = Path(_PERSIST_PATH)
    if not path.exists():
        return 0
    # A polygon-heavy dump can be hundreds of MB and OOM the API on boot — which
    # surfaces in the UI as "LandSignal API is not reachable".
    try:
        size = path.stat().st_size
    except OSError:
        return 0
    # Hard ceiling for pathological dumps (pre-slim polygons / GIS attribute blobs).
    # Slim nationwide snapshots of ~100k parcels can legitimately be 100–250MB.
    if size > 400_000_000:
        structlog.get_logger().warning(
            "persist_skip_too_large",
            path=str(path),
            bytes=size,
            note="Quarantined fat inventory dump; starting empty so API stays reachable.",
        )
        try:
            path.rename(str(path) + ".oom-bak")
        except OSError:
            pass
        return 0
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return 0
    from landsignal.services.memory_guard import slim_listing_raw
    from landsignal.services.parcel_outline import compact_polygon

    n = 0
    for raw in payload.get("parcels") or []:
        try:
            if isinstance(raw, dict):
                raw = {**raw, "polygon": compact_polygon(raw.get("polygon"))}
            p = ParcelRecord.model_validate(raw)
            # Never restore invented acreage squares.
            p.polygon = compact_polygon(p.polygon)
            store.parcels[p.id] = p
            n += 1
        except Exception:
            continue
    for raw in payload.get("listings") or []:
        try:
            if isinstance(raw, dict) and isinstance(raw.get("raw"), dict):
                raw = {**raw, "raw": slim_listing_raw(raw["raw"])}
            L = ListingRecord.model_validate(raw)
            # $0 bids are missing prices — never treat as free land
            if L.asking_price_usd is not None and L.asking_price_usd <= 0:
                L.asking_price_usd = None
            L.raw = slim_listing_raw(L.raw if isinstance(L.raw, dict) else {})
            # Every state: promote nested CAD land values into ask so budget filters work.
            from landsignal.services.assessed_price import backfill_listing_ask_from_assessed

            backfill_listing_ask_from_assessed(L)
            store.listings[L.id] = L
            store.index_listing(L)
        except Exception:
            continue
    store.rebuild_listing_index()
    for pid_s, scores in (payload.get("scores") or {}).items():
        try:
            pid = UUID(pid_s)
            store.scores[pid] = [ScoreRecord.model_validate(s) for s in scores]
        except Exception:
            continue
    if payload.get("investor_profile"):
        store.investor_profile.update(payload["investor_profile"])
    for raw in payload.get("land_alert_profiles") or []:
        try:
            p = LandAlertProfile.model_validate(raw)
            store.land_alert_profiles[p.id] = p
        except Exception:
            continue
    for raw in payload.get("land_alert_matches") or []:
        try:
            m = LandAlertMatch.model_validate(raw)
            store.land_alert_matches[f"{m.profile_id}:{m.parcel_id}"] = m
        except Exception:
            continue
    for raw in payload.get("alerts") or []:
        try:
            store.alerts.append(AlertRecord.model_validate(raw))
        except Exception:
            continue
    for raw in payload.get("alert_rules") or []:
        try:
            r = AlertRuleRecord.model_validate(raw)
            store.alert_rules[r.id] = r
        except Exception:
            continue
    return n


def get_store(seed_demo: bool = False) -> MemoryStore:
    global _STORE
    if _STORE is None:
        _STORE = MemoryStore()
        loaded = load_persisted_store(_STORE)
        if loaded:
            import structlog

            structlog.get_logger().info("store_restored_from_disk", parcels=loaded)
        elif seed_demo:
            _STORE.seed_demo()
    return _STORE


def reset_store() -> None:
    global _STORE
    _STORE = None
