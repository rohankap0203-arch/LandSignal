"""Preference-driven Land Alerts — soft match scores against MemoryStore inventory."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import structlog

from landsignal.models import (
    AlertRecord,
    LandAlertMatch,
    LandAlertNotify,
    LandAlertProfile,
    LandAlertProfileUpsert,
    ListingRecord,
    ParcelRecord,
    ScoreRecord,
)
from landsignal.settings import Settings, get_settings
from landsignal.store import MemoryStore

log = structlog.get_logger()

DEMO_USER_ID = UUID("00000000-0000-4000-8000-000000000002")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def _norm(s: Any) -> str:
    return str(s or "").strip().lower()


def _prefs(profile: LandAlertProfile) -> dict[str, Any]:
    return profile.preferences or {}


def _mode(prefs: dict[str, Any], key: str, default: str = "prefer") -> str:
    return _norm(prefs.get(key) or default) or default


def _match_key(profile_id: UUID, parcel_id: UUID) -> str:
    return f"{profile_id}:{parcel_id}"


def _state_codes(states: list[Any]) -> set[str]:
    aliases = {
        "north carolina": "nc",
        "south carolina": "sc",
        "tennessee": "tn",
        "georgia": "ga",
        "florida": "fl",
        "texas": "tx",
        "virginia": "va",
        "alabama": "al",
        "mississippi": "ms",
        "arkansas": "ar",
        "louisiana": "la",
        "kentucky": "ky",
        "oklahoma": "ok",
        "missouri": "mo",
        "ohio": "oh",
        "indiana": "in",
        "illinois": "il",
        "michigan": "mi",
        "wisconsin": "wi",
        "iowa": "ia",
        "minnesota": "mn",
        "pennsylvania": "pa",
        "new york": "ny",
        "new jersey": "nj",
        "massachusetts": "ma",
        "connecticut": "ct",
        "maryland": "md",
        "west virginia": "wv",
    }
    out: set[str] = set()
    for s in states or []:
        w = _norm(s)
        if not w:
            continue
        if len(w) == 2:
            out.add(w)
        else:
            out.add(aliases.get(w, w))
    return out


def _range_score(
    value: float | None,
    lo: float | None,
    hi: float | None,
    mode: str,
    label: str,
    unit: str = "",
) -> tuple[float, str | None, bool]:
    if value is None or (lo is None and hi is None):
        return 100.0, None, False
    lo_v = float(lo) if lo is not None else float(value)
    hi_v = float(hi) if hi is not None else float(value)
    if lo_v <= value <= hi_v:
        return 100.0, f"{label}: {value:g}{unit} within preferred {lo_v:g}–{hi_v:g}{unit}", False
    span = max(hi_v - lo_v, 1.0)
    dist = ((lo_v - value) / span) if value < lo_v else ((value - hi_v) / span)
    if mode == "must":
        if dist <= 0.08:
            return 70.0, f"{label}: {value:g}{unit} slightly outside must-have {lo_v:g}–{hi_v:g}{unit}", True
        return 0.0, f"{label}: {value:g}{unit} outside must-have {lo_v:g}–{hi_v:g}{unit}", True
    if mode == "flexible":
        return _clamp(100 - dist * 35), f"{label}: {value:g}{unit} vs preferred {lo_v:g}–{hi_v:g}{unit}", dist > 0.25
    return _clamp(100 - dist * 55), f"{label}: {value:g}{unit} vs preferred {lo_v:g}–{hi_v:g}{unit}", dist > 0.15


def score_parcel_against_profile(
    store: MemoryStore,
    parcel: ParcelRecord,
    profile: LandAlertProfile,
    score: ScoreRecord | None = None,
    listing: ListingRecord | None = None,
) -> dict[str, Any]:
    prefs = _prefs(profile)
    listing = listing or store.listing_for_parcel(parcel.id)
    score = score or store.latest_score(parcel.id)
    ls_score = float(score.opportunity) if score else 50.0
    ask = listing.asking_price_usd if listing else None
    ppa = listing.price_per_acre_usd if listing else None
    if ppa is None and ask and parcel.acreage:
        ppa = ask / parcel.acreage

    weights: list[tuple[float, float]] = []
    reasons: list[str] = []
    watches: list[str] = []
    hard_fail = False

    # States
    states = list(prefs.get("states") or [])
    st_mode = _mode(prefs, "states_mode", "must" if states else "flexible")
    if states:
        wanted = _state_codes(states)
        st = _norm(parcel.state)
        if st in wanted:
            weights.append((2.2, 100.0))
            reasons.append(f"Within your preferred {parcel.state} region")
        else:
            se = {"nc", "sc", "tn", "ga", "va", "al", "ky", "wv"}
            if st in se and wanted & se:
                weights.append((2.2, 55.0))
                watches.append(f"Near your preferred region ({parcel.state})")
            else:
                weights.append((2.2, 0.0))
                watches.append(f"Outside preferred states ({parcel.state or 'n/a'})")
                if st_mode == "must":
                    hard_fail = True

    # Budget
    budget_min = prefs.get("budget_min")
    budget_max = prefs.get("budget_max")
    budget_mode = _mode(prefs, "budget_mode", "prefer")
    b_score, b_reason, b_watch = _range_score(ask, None, budget_max, budget_mode, "Price")
    if budget_max is not None and ask is not None and ask <= float(budget_max):
        under = float(budget_max) - ask
        if under >= 1000:
            reasons.append(f"${under:,.0f} below your target acquisition budget")
        else:
            reasons.append(f"${ask:,.0f} within your acquisition budget")
    elif b_reason:
        (watches if b_watch else reasons).append(b_reason)
    if budget_min is not None and ask is not None and ask < float(budget_min) * 0.4:
        watches.append("Asking price is far below your typical ticket size — verify condition / title")
    if budget_mode == "must" and b_score < 40:
        hard_fail = True
    weights.append((2.0 if budget_max is not None else 0.4, b_score))

    # Acreage
    acres_min = prefs.get("acres_min")
    acres_max = prefs.get("acres_max")
    acres_mode = _mode(prefs, "acres_mode", "prefer")
    a_score, a_reason, a_watch = _range_score(
        parcel.acreage, acres_min, acres_max, acres_mode, "Acreage", unit=" acres"
    )
    if a_reason:
        (watches if a_watch else reasons).append(a_reason)
    if acres_mode == "must" and a_score < 40:
        hard_fail = True
    weights.append((1.8 if (acres_min is not None or acres_max is not None) else 0.3, a_score))

    # Price / acre
    ppa_min = prefs.get("price_per_acre_min")
    ppa_max = prefs.get("price_per_acre_max")
    if ppa is not None and (ppa_min is not None or ppa_max is not None):
        p_score, p_reason, p_watch = _range_score(ppa, ppa_min, ppa_max, "prefer", "Price/acre", unit="/ac")
        weights.append((1.2, p_score))
        if p_reason:
            (watches if p_watch else reasons).append(p_reason)

    # Land types / use
    land_types = [_norm(x) for x in (prefs.get("land_types") or []) if x]
    if land_types:
        blob = " ".join(
            [
                _norm(parcel.land_use),
                _norm(parcel.zoning),
                _norm(listing.title if listing else None),
                _norm(listing.description if listing else None),
            ]
        )
        if any(t in blob for t in land_types):
            weights.append((1.4, 100.0))
            reasons.append(f"Land type aligns ({parcel.land_use or 'land'})")
        elif any(k in blob for k in ("vacant", "raw", "ag", "farm", "rural", "land")):
            weights.append((1.4, 72.0))
            reasons.append("General land use is close to your preferred types")
        else:
            weights.append((1.4, 40.0))
            watches.append("Land type differs from preferred types")

    # Strategies
    strategies = [_norm(x).replace(" ", "_") for x in (prefs.get("strategies") or []) if x]
    if strategies and score:
        best = _norm(score.best_strategy.value if score.best_strategy else "")
        strat_scores = { _norm(k): float(v) for k, v in (score.strategy_scores or {}).items() }
        hit = None
        for s in strategies:
            aliases = {
                "land_banking": "land_bank",
                "landbanking": "land_bank",
                "speculation": "land_bank",
                "farmland": "farmland",
                "agricultural": "farmland",
                "recreational": "recreational",
                "residential_development": "development",
                "commercial_development": "development",
                "development": "development",
                "timber": "timber",
                "natural_resources": "timber",
                "energy": "energy",
            }
            key = aliases.get(s, s)
            if best == key or (strat_scores.get(key, 0) >= 55):
                hit = key
                break
        if hit:
            weights.append((1.6, 92.0))
            reasons.append(f"Matches your {hit.replace('_', ' ')} strategy")
        else:
            weights.append((1.6, 48.0))
            watches.append("Strategy fit is adjacent — scored softly")

    # Interests (bonus)
    interests = prefs.get("interests") or {}
    interest_checks = [
        ("agricultural", ["farm", "ag", "agriculture", "pasture", "crop"], "Agricultural / farmland interest"),
        ("recreational", ["hunt", "recreation", "cabin", "lake", "river"], "Recreational land interest"),
        ("residential_dev", ["residential", "homesite", "subdivision", "buildable"], "Residential development interest"),
        ("commercial_dev", ["commercial", "retail", "industrial"], "Commercial development interest"),
        ("timber", ["timber", "forest", "woods"], "Timber / natural-resource interest"),
        ("land_banking", ["vacant", "raw", "hold", "land bank"], "Land-banking / speculation interest"),
        ("development", ["develop", "buildable", "subdivision"], "Development interest"),
    ]
    blob = " ".join(
        [
            _norm(parcel.land_use),
            _norm(listing.title if listing else None),
            _norm(listing.description if listing else None),
            " ".join(_norm(x) for x in (score.why_interesting if score else [])),
        ]
    )
    bonus = 0.0
    for key, keys, label in interest_checks:
        if interests.get(key) and any(k in blob for k in keys):
            bonus += 4.0
            reasons.append(label)
    bonus = min(12.0, bonus)

    # Infrastructure
    infra = [_norm(x) for x in (prefs.get("infrastructure_prefs") or []) if x]
    if infra:
        access = store.enrichments.get(parcel.id)
        access_blob = ""
        if access and access.access.value is not None:
            access_blob = _norm(access.access.value)
        if any(x in infra for x in ("road_access", "road", "access", "paved")):
            if "road" in access_blob or "access" in blob or (score and score.opportunity >= 70):
                weights.append((1.0, 88.0))
                reasons.append("Strong road-access characteristics")
            else:
                weights.append((1.0, 55.0))
                watches.append("Road access not fully confirmed in open data")

    # Risk comfort
    max_risk = _norm(prefs.get("max_risk"))
    if score and max_risk:
        cap = {"low": 35, "moderate": 55, "high": 75, "very_high": 100}.get(max_risk, 55)
        if score.risk <= cap:
            weights.append((0.8, 90.0))
        else:
            weights.append((0.8, 42.0))
            watches.append(f"Risk score ({score.risk:.0f}) above your comfort band")

    # Hold period soft
    hold_min = prefs.get("hold_years_min")
    hold_max = prefs.get("hold_years_max")
    if score and (hold_min is not None or hold_max is not None):
        # LAND_BANK / long hold strategies align with longer holds
        if score.best_strategy and score.best_strategy.value in ("LAND_BANK", "TIMBER", "FARMLAND"):
            reasons.append("Holding profile aligns with longer-term land strategies")
            weights.append((0.6, 85.0))
        else:
            weights.append((0.6, 60.0))

    active = [(w, s) for w, s in weights if w > 0]
    if not active:
        pref = 70.0 + min(20.0, ls_score / 5)
    else:
        pref = sum(w * s for w, s in active) / sum(w for w, _ in active)
    pref = _clamp(pref + bonus)

    # Exceptional opportunity can lift a near-miss (soft discovery, not rigid filters)
    if ls_score >= 85 and pref >= 45:
        pref = _clamp(pref + 8)
        reasons.append("Exceptional LandSignal opportunity characteristics")
    elif ls_score >= 75 and pref >= 50:
        pref = _clamp(pref + 4)

    if hard_fail and pref > 35:
        pref = min(pref, 35.0)

    # Dynamic acquisition intel (always useful under Watch)
    intel: list[str] = []
    if listing and listing.days_on_market is not None:
        dom = int(listing.days_on_market)
        if dom <= 14:
            intel.append(f"Fresh to market · {dom} days listed")
        elif dom >= 120:
            intel.append(f"Long exposure · {dom} days on market — possible seller fatigue")
        else:
            intel.append(f"{dom} days on market")
    if listing and listing.price_per_acre_usd and parcel.acreage:
        intel.append(f"${listing.price_per_acre_usd:,.0f}/acre asking screen")
    elif ask and parcel.acreage:
        intel.append(f"${ask / parcel.acreage:,.0f}/acre implied")
    if score:
        if score.asking_discount_pct is not None:
            d = score.asking_discount_pct
            if d >= 15:
                intel.append(f"~{d:.0f}% under LandSignal value screen")
            elif d <= -10:
                intel.append(f"Asking ~{abs(d):.0f}% above LandSignal value screen")
        if score.confidence is not None:
            if score.confidence < 45:
                intel.append(f"Thin file confidence ({score.confidence:.0f}) — verify before capital")
            elif score.confidence >= 70:
                intel.append(f"Solid file confidence ({score.confidence:.0f})")
        if score.deal_readiness is not None and score.deal_readiness < 40:
            intel.append("Deal readiness is early — expect diligence friction")
        for kill in (score.what_could_kill or [])[:2]:
            if kill:
                watches.append(str(kill))
        if score.best_strategy:
            intel.append(f"Engine leans {score.best_strategy.value.replace('_', ' ').title()}")
    if listing and listing.status and _norm(listing.status) not in ("active", ""):
        intel.append(f"Listing status: {listing.status}")

    seen: set[str] = set()
    clean_reasons: list[str] = []
    for r in reasons:
        if r and r not in seen:
            seen.add(r)
            clean_reasons.append(r)
    clean_watches: list[str] = []
    for w in watches:
        if w and w not in seen:
            seen.add(w)
            clean_watches.append(w)
    clean_intel: list[str] = []
    for line in intel:
        if line and line not in seen:
            seen.add(line)
            clean_intel.append(line)

    qualifies = (not hard_fail and pref >= 55) or (pref >= 70 and ls_score >= 65)
    return {
        "preference_match_pct": round(pref, 1),
        "landsignal_score": round(ls_score, 1),
        "why_matched": clean_reasons[:6],
        "watch_flags": clean_watches[:4],
        "intel_notes": clean_intel[:5],
        "qualifies": qualifies,
        "hard_fail": hard_fail,
    }


def upsert_match(
    store: MemoryStore,
    profile: LandAlertProfile,
    parcel: ParcelRecord,
    *,
    origin: str,
    score: ScoreRecord | None = None,
    update_kind: str | None = None,
) -> LandAlertMatch | None:
    result = score_parcel_against_profile(store, parcel, profile, score=score)
    key = _match_key(profile.id, parcel.id)
    if not result["qualifies"]:
        store.land_alert_matches.pop(key, None)
        return None

    existing = store.land_alert_matches.get(key)
    now = _utcnow()
    is_new_discovery = origin == "new_discovery"

    if existing:
        status = existing.status
        if existing.status == "viewed":
            status = "viewed"
        elif is_new_discovery or origin == "price_update":
            status = "new"
        match = existing.model_copy(
            update={
                "preference_match_pct": result["preference_match_pct"],
                "landsignal_score": result["landsignal_score"],
                "why_matched": result["why_matched"],
                "watch_flags": result["watch_flags"],
                "status": status,
                "origin": origin if is_new_discovery else existing.origin,
                "is_new_discovery": existing.is_new_discovery or is_new_discovery,
                "update_kind": update_kind or existing.update_kind,
                "qualified_for_alert": True,
                "updated_at": now,
            }
        )
    else:
        status = "new" if is_new_discovery else "unseen"
        kind = update_kind or ("new_listing" if is_new_discovery else None)
        prior_alert = _existing_land_alert(
            store,
            parcel_id=parcel.id,
            profile_id=profile.id,
            update_kind=kind,
        )
        match = LandAlertMatch(
            profile_id=profile.id,
            user_id=profile.user_id,
            parcel_id=parcel.id,
            preference_match_pct=result["preference_match_pct"],
            landsignal_score=result["landsignal_score"],
            why_matched=result["why_matched"],
            watch_flags=result["watch_flags"],
            status=status,
            origin=origin,
            is_new_discovery=is_new_discovery,
            update_kind=kind,
            qualified_for_alert=True,
            notified=bool(prior_alert),
            notified_at=prior_alert.created_at if prior_alert else None,
            notification_channels=list(prior_alert.delivered_channels) if prior_alert else [],
            created_at=now,
            updated_at=now,
        )
    store.land_alert_matches[key] = match
    return match


def rescan_profile(store: MemoryStore, profile: LandAlertProfile, *, origin: str = "existing_inventory") -> list[LandAlertMatch]:
    out: list[LandAlertMatch] = []
    if profile.paused or not profile.active:
        return out
    # Index by state first when profile has state constraints
    prefs = _prefs(profile)
    wanted = _state_codes(list(prefs.get("states") or []))
    st_mode = _mode(prefs, "states_mode", "must" if wanted else "flexible")
    for parcel in store.parcels.values():
        if wanted and st_mode == "must" and _norm(parcel.state) not in wanted:
            # Still allow soft SE neighbors via score_parcel — skip only hard far misses for speed
            se = {"nc", "sc", "tn", "ga", "va", "al", "ky", "wv"}
            if not (_norm(parcel.state) in se and wanted & se):
                continue
        m = upsert_match(store, profile, parcel, origin=origin)
        if m:
            out.append(m)
    return out


def match_parcel(
    store: MemoryStore,
    parcel_id: UUID,
    *,
    origin: str = "new_discovery",
    update_kind: str | None = None,
    settings: Settings | None = None,
) -> list[LandAlertMatch]:
    """Score one parcel against all active profiles (called after analyze)."""
    settings = settings or get_settings()
    parcel = store.parcels.get(parcel_id)
    if not parcel:
        return []
    score = store.latest_score(parcel_id)
    created: list[LandAlertMatch] = []
    for profile in store.land_alert_profiles.values():
        if profile.paused or not profile.active:
            continue
        m = upsert_match(
            store,
            profile,
            parcel,
            origin=origin,
            score=score,
            update_kind=update_kind,
        )
        if m:
            created.append(m)
            if origin in ("new_discovery", "price_update"):
                _maybe_notify(store, profile, m, parcel, settings)
    return created


def _sensitivity_threshold(level: str) -> float:
    return {"exceptional": 90.0, "strong": 75.0, "all": 55.0}.get(_norm(level), 75.0)


def _parcel_has_real_boundary(parcel: ParcelRecord | None) -> bool:
    """True only for a real closed ring — never accept pin-only or invented squares as enough."""
    if not parcel or not parcel.polygon:
        return False
    try:
        ring = parcel.polygon[0]
    except (IndexError, TypeError):
        return False
    if not isinstance(ring, list) or len(ring) < 4:
        return False
    # Require valid lon/lat pairs
    ok = 0
    for pt in ring:
        if not isinstance(pt, (list, tuple)) or len(pt) < 2:
            continue
        lon, lat = pt[0], pt[1]
        if (
            isinstance(lat, (int, float))
            and isinstance(lon, (int, float))
            and abs(lat) <= 90
            and abs(lon) <= 180
        ):
            ok += 1
    return ok >= 4


def _parcel_is_mappable(parcel: ParcelRecord | None) -> bool:
    if not parcel:
        return False
    if parcel.latitude is None or parcel.longitude is None:
        return False
    if not (-90 <= parcel.latitude <= 90 and -180 <= parcel.longitude <= 180):
        return False
    return _parcel_has_real_boundary(parcel)


def _existing_land_alert(
    store: MemoryStore,
    *,
    parcel_id: UUID,
    profile_id: UUID,
    update_kind: str | None = None,
) -> AlertRecord | None:
    """One in-app notification per parcel — any prior alert for that land counts as sent."""
    del update_kind  # kept for call-site compatibility; no longer splits duplicates
    del profile_id
    for alert in store.alerts:
        if alert.severity == "LAND_ALERT" and alert.parcel_id == parcel_id:
            return alert
    return None


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _clamp_not_future(dt: datetime) -> datetime:
    now = _utcnow()
    aware = _as_utc(dt) or now
    # Never surface a scouted/retrieved time ahead of real UTC now.
    return aware if aware <= now else now


def dedupe_land_alert_records(alerts: list[AlertRecord]) -> list[AlertRecord]:
    """Keep newest LAND_ALERT per parcel + per property/location identity."""
    seen_parcel: set[str] = set()
    seen_prop: set[str] = set()
    out: list[AlertRecord] = []
    for alert in alerts:
        if alert.severity != "LAND_ALERT":
            out.append(alert)
            continue
        body = alert.body or {}
        parcel_key = str(alert.parcel_id)
        prop_key = f"{_norm(body.get('property'))}|{_norm(body.get('location'))}"
        if parcel_key in seen_parcel:
            continue
        if prop_key != "|" and prop_key in seen_prop:
            continue
        seen_parcel.add(parcel_key)
        if prop_key != "|":
            seen_prop.add(prop_key)
        out.append(alert)
    return out


def curate_land_alert_feed(store: MemoryStore) -> list[AlertRecord]:
    """Dedupe + drop alerts for parcels that are unmappable or no longer matching."""
    curated: list[AlertRecord] = []
    for alert in dedupe_land_alert_records(list(store.alerts)):
        if alert.severity != "LAND_ALERT":
            curated.append(alert)
            continue
        parcel = store.parcels.get(alert.parcel_id)
        if not _parcel_is_mappable(parcel):
            continue
        body = dict(alert.body or {})
        profile_id = str(body.get("profile_id") or "")
        # Must still be a live qualifying match for that profile (or any profile if unset).
        live = False
        for match in store.land_alert_matches.values():
            if match.parcel_id != alert.parcel_id:
                continue
            if profile_id and str(match.profile_id) != profile_id:
                continue
            if match.qualified_for_alert and match.preference_match_pct >= 55:
                live = True
                break
        if not live:
            continue
        # Normalize scouted timestamps to real UTC, never in the future.
        scouted = _clamp_not_future(
            _as_utc(_parse_iso(body.get("scouted_at")) or alert.created_at) or _utcnow()
        )
        body["scouted_at"] = scouted.isoformat().replace("+00:00", "Z")
        body["retrieved_at"] = body["scouted_at"]
        body["has_boundary"] = True
        curated.append(alert.model_copy(update={"body": body, "created_at": _clamp_not_future(_as_utc(alert.created_at) or scouted)}))
    return curated


def _parse_iso(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _listing_scouted_at(listing: ListingRecord | None, match: LandAlertMatch) -> datetime:
    """When LandSignal actually retrieved/scouted this land for the alert — not vendor listed_at."""
    now = _utcnow()
    # Prefer our ingest/seen time; never trust listed_at alone (often wrong/future in feeds).
    for value in (
        (listing.last_seen_at if listing else None),
        (listing.created_at if listing else None),
        match.created_at,
        match.updated_at,
        now,
    ):
        aware = _as_utc(value)
        if aware is None:
            continue
        return _clamp_not_future(aware)
    return now


def _maybe_notify(
    store: MemoryStore,
    profile: LandAlertProfile,
    match: LandAlertMatch,
    parcel: ParcelRecord,
    settings: Settings,
) -> None:
    if match.notified:
        return
    # Preference-change / inventory rescan must not spam "new property" notifications
    if match.origin not in ("new_discovery", "price_update"):
        return
    kind = _norm(match.update_kind or "")
    if kind in ("new_data", "status_change"):
        return
    if kind not in ("new_listing", "price_drop", "price_increase", ""):
        return
    # No pin-only / boundary-less parcels in the notification feed.
    if not _parcel_is_mappable(parcel):
        return
    if not match.qualified_for_alert or match.preference_match_pct < 55:
        return
    # Full legitimacy gate: never re-emit the same parcel if history already has it
    # (covers match drop/recreate cycles that reset match.notified).
    prior = _existing_land_alert(
        store,
        parcel_id=parcel.id,
        profile_id=profile.id,
        update_kind=match.update_kind,
    )
    if prior:
        store.land_alert_matches[_match_key(profile.id, parcel.id)] = match.model_copy(
            update={
                "notified": True,
                "notified_at": prior.created_at or match.notified_at or _utcnow(),
                "notification_channels": list(prior.delivered_channels or match.notification_channels),
            }
        )
        return

    notify = profile.notify or LandAlertNotify()
    if match.preference_match_pct < _sensitivity_threshold(notify.sensitivity):
        return
    # Exceptional override for digest users
    immediate_override = match.preference_match_pct >= 92 and match.landsignal_score >= 85

    channels: list[str] = []
    freq = _norm(notify.frequency)
    if freq == "in_app_only":
        if notify.in_app:
            channels.append("IN_APP")
    elif freq in ("daily_digest", "weekly_digest") and not immediate_override:
        if notify.in_app:
            channels.append("IN_APP")
        channels.append(f"DIGEST:{freq}")
    else:
        if notify.in_app:
            channels.append("IN_APP")
        if notify.email:
            channels.append("EMAIL" if settings.smtp_url else "EMAIL:NOT_CONFIGURED")
        if notify.sms:
            configured = bool(
                settings.twilio_account_sid and settings.twilio_auth_token and settings.twilio_from_number
            )
            channels.append("SMS" if configured else "SMS:NOT_CONFIGURED")
        if notify.push:
            channels.append("PUSH:NOT_CONFIGURED")

    if not channels:
        return

    listing = store.listing_for_parcel(parcel.id)
    acres = f"{parcel.acreage:g} acres" if parcel.acreage else "Land"
    price = f"${listing.asking_price_usd:,.0f}" if listing and listing.asking_price_usd else "Price n/a"
    kind_label = {
        "price_drop": "Price drop",
        "price_increase": "Price increase",
        "status_change": "Status change",
        "new_data": "New data",
        "new_listing": "New listing",
    }.get(match.update_kind or "", "New Land Signal")
    # Scouted = when we are issuing this real notification (UTC), not a vendor clock.
    scouted_at = _clamp_not_future(_listing_scouted_at(listing, match))
    scouted_iso = scouted_at.isoformat().replace("+00:00", "Z")
    title = f"{kind_label} — {match.preference_match_pct:.0f}% Match"
    body = {
        "property": (listing.title if listing else None) or parcel.apn or str(parcel.id),
        "location": f"{parcel.county or ''}, {parcel.state or ''}".strip(", "),
        "acres": parcel.acreage,
        "price": listing.asking_price_usd if listing else None,
        "preference_match_pct": match.preference_match_pct,
        "landsignal_score": match.landsignal_score,
        "why_matched": match.why_matched[:3],
        "watch_flags": match.watch_flags[:2],
        "summary": f"{acres} • {parcel.state or 'US'} • {price}. Strong match for your land profile.",
        "deep_link": f"/parcels/{parcel.id}",
        "profile_id": str(profile.id),
        "match_id": str(match.id),
        "update_kind": match.update_kind,
        "scouted_at": scouted_iso,
        "retrieved_at": scouted_iso,
        "has_boundary": True,
        "delivery": {
            "in_app": "delivered" if any(c.startswith("IN_APP") for c in channels) else "skipped",
            "email": (
                "delivered"
                if "EMAIL" in channels
                else ("pending_provider" if any(c.startswith("EMAIL") for c in channels) else "skipped")
            ),
            "sms": (
                "delivered"
                if "SMS" in channels
                else ("pending_provider" if any(c.startswith("SMS") for c in channels) else "skipped")
            ),
        },
    }
    alert = AlertRecord(
        rule_id=None,
        parcel_id=parcel.id,
        severity="LAND_ALERT",
        title=title,
        body=body,
        delivered_channels=channels,
    )
    store.alerts.insert(0, alert)
    # Prune historical duplicates / illegitimate rows so the feed stays accurate
    store.alerts[:] = curate_land_alert_feed(store)
    store.land_alert_matches[_match_key(profile.id, parcel.id)] = match.model_copy(
        update={
            "notified": True,
            "notified_at": _utcnow(),
            "notification_channels": channels,
        }
    )
    log.info(
        "land_alert_queued",
        profile_id=str(profile.id),
        parcel_id=str(parcel.id),
        match=match.preference_match_pct,
        channels=channels,
    )


def upsert_profile(
    store: MemoryStore,
    body: LandAlertProfileUpsert,
    user_id: UUID = DEMO_USER_ID,
) -> tuple[LandAlertProfile, list[LandAlertMatch]]:
    now = _utcnow()
    existing = store.land_alert_profiles.get(body.id) if body.id else None
    if existing and existing.user_id != user_id:
        existing = None

    if existing:
        profile = existing.model_copy(
            update={
                "name": body.name or existing.name,
                "preferences": body.preferences if body.preferences is not None else existing.preferences,
                "notify": body.notify or existing.notify,
                "paused": existing.paused if body.paused is None else body.paused,
                "updated_at": now,
            }
        )
        origin = "preference_change"
    else:
        profile = LandAlertProfile(
            id=body.id or uuid4(),
            user_id=user_id,
            name=body.name or "My Land Alert",
            preferences=body.preferences or {},
            notify=body.notify or LandAlertNotify(),
            paused=bool(body.paused) if body.paused is not None else False,
            created_at=now,
            updated_at=now,
        )
        origin = "existing_inventory"

    store.land_alert_profiles[profile.id] = profile
    matches = rescan_profile(store, profile, origin=origin)
    try:
        from landsignal.store import persist_store

        persist_store(store)
    except Exception:  # noqa: BLE001
        pass
    return profile, matches


def set_paused(store: MemoryStore, profile_id: UUID, paused: bool, user_id: UUID = DEMO_USER_ID) -> LandAlertProfile:
    profile = store.land_alert_profiles.get(profile_id)
    if not profile or profile.user_id != user_id:
        raise KeyError("profile")
    profile = profile.model_copy(update={"paused": paused, "updated_at": _utcnow()})
    store.land_alert_profiles[profile_id] = profile
    return profile


def mark_match_viewed(store: MemoryStore, user_id: UUID, parcel_id: UUID) -> int:
    n = 0
    now = _utcnow()
    for key, m in list(store.land_alert_matches.items()):
        if m.user_id == user_id and m.parcel_id == parcel_id and m.status != "viewed":
            store.land_alert_matches[key] = m.model_copy(
                update={"status": "viewed", "viewed_at": now, "updated_at": now}
            )
            n += 1
    return n


def mark_match_unviewed(store: MemoryStore, user_id: UUID, parcel_id: UUID) -> int:
    """Undo viewed — restore to unseen (or new if it was a discovery)."""
    n = 0
    now = _utcnow()
    for key, m in list(store.land_alert_matches.items()):
        if m.user_id == user_id and m.parcel_id == parcel_id and m.status == "viewed":
            status = "new" if m.is_new_discovery else "unseen"
            store.land_alert_matches[key] = m.model_copy(
                update={"status": status, "viewed_at": None, "updated_at": now}
            )
            n += 1
    return n


def mark_all_seen(store: MemoryStore, user_id: UUID, profile_id: UUID | None = None) -> int:
    n = 0
    now = _utcnow()
    for key, m in list(store.land_alert_matches.items()):
        if m.user_id != user_id:
            continue
        if profile_id and m.profile_id != profile_id:
            continue
        if m.status in ("new", "unseen"):
            store.land_alert_matches[key] = m.model_copy(
                update={"status": "viewed", "viewed_at": now, "updated_at": now}
            )
            n += 1
    return n


def mark_all_unseen(store: MemoryStore, user_id: UUID, profile_id: UUID | None = None) -> int:
    """Undo mark-all-seen — restore viewed matches to unseen/new."""
    n = 0
    now = _utcnow()
    for key, m in list(store.land_alert_matches.items()):
        if m.user_id != user_id:
            continue
        if profile_id and m.profile_id != profile_id:
            continue
        if m.status == "viewed":
            status = "new" if m.is_new_discovery else "unseen"
            store.land_alert_matches[key] = m.model_copy(
                update={"status": status, "viewed_at": None, "updated_at": now}
            )
            n += 1
    return n


def matches_for_user(
    store: MemoryStore,
    user_id: UUID = DEMO_USER_ID,
    profile_id: UUID | None = None,
) -> list[LandAlertMatch]:
    rows = [
        m
        for m in store.land_alert_matches.values()
        if m.user_id == user_id and (profile_id is None or m.profile_id == profile_id)
    ]
    rank = {"new": 0, "unseen": 1, "viewed": 2}
    rows.sort(key=lambda m: (rank.get(m.status, 9), -m.preference_match_pct, -m.landsignal_score))
    return rows


def _imagery_url(lat: float | None, lon: float | None, acres: float | None = None) -> str | None:
    """Esri World Imagery snapshot centered on the parcel (no Mapbox required)."""
    if lat is None or lon is None:
        return None
    # Wider frame for larger tracts; keep tight for small lots
    pad = 0.008
    if acres is not None and acres > 0:
        pad = max(0.0035, min(0.035, (float(acres) ** 0.5) * 0.0012))
    return (
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export"
        f"?bbox={lon - pad},{lat - pad},{lon + pad},{lat + pad}"
        "&bboxSR=4326&imageSR=4326&size=640,120&format=jpg&f=image"
    )


def match_card(store: MemoryStore, match: LandAlertMatch) -> dict[str, Any]:
    from landsignal.services.presentation import sourcing_card

    parcel = store.parcels.get(match.parcel_id)
    listing = store.listing_for_parcel(match.parcel_id) if parcel else None
    score = store.latest_score(match.parcel_id) if parcel else None
    ask = listing.asking_price_usd if listing else None
    acres = parcel.acreage if parcel else None
    ppa = listing.price_per_acre_usd if listing else None
    if ppa is None and ask and acres:
        ppa = ask / acres
    source = (
        sourcing_card(
            provider_id=listing.provider_id if listing else None,
            source_url=listing.source_url if listing else None,
            title=(listing.title if listing else None) or "",
            apn=parcel.apn if parcel else None,
            state=parcel.state if parcel else None,
            county=parcel.county if parcel else None,
            latitude=parcel.latitude if parcel else None,
            longitude=parcel.longitude if parcel else None,
            raw=listing.raw if listing else None,
        )
        if parcel
        else {}
    )
    links = list(source.get("links") or [])
    find = next((L for L in links if L.get("kind") == "lookup" and L.get("available") is not False), None)
    primary = next((L for L in links if L.get("kind") == "primary" and L.get("available") is not False), None)
    website = source.get("website") or (primary.get("url") if primary else None) or (
        listing.source_url if listing else None
    )
    phone = source.get("phone")
    imagery_url = _imagery_url(
        parcel.latitude if parcel else None,
        parcel.longitude if parcel else None,
        acres,
    )

    return {
        "id": str(match.id),
        "profile_id": str(match.profile_id),
        "parcel_id": str(match.parcel_id),
        "status": match.status,
        "origin": match.origin,
        "is_new_discovery": match.is_new_discovery,
        "update_kind": match.update_kind,
        "preference_match_pct": match.preference_match_pct,
        "landsignal_score": match.landsignal_score,
        "why_matched": match.why_matched,
        "watch_flags": match.watch_flags,
        "imagery_url": imagery_url,
        "latitude": parcel.latitude if parcel else None,
        "longitude": parcel.longitude if parcel else None,
        "has_boundary": _parcel_has_real_boundary(parcel),
        # Polygon omitted from list cards (multi‑MB payload). Viewer loads it via /parcels/{id}/geometry.
        "polygon": None,
        "viewed_at": match.viewed_at.isoformat() if match.viewed_at else None,
        "created_at": match.created_at.isoformat() if match.created_at else None,
        "updated_at": match.updated_at.isoformat() if match.updated_at else None,
        "property_name": (listing.title if listing else None)
        or (parcel.apn if parcel else None)
        or "Land parcel",
        "location": (
            f"{parcel.county}, {parcel.state}" if parcel and parcel.county else (parcel.state if parcel else "")
        ),
        "state": parcel.state if parcel else None,
        "county": parcel.county if parcel else None,
        "asking_price": ask,
        "asking_price_display": f"${ask:,.0f}" if ask is not None else None,
        "acres": acres,
        "acres_display": f"{acres:g} acres" if acres is not None else None,
        "price_per_acre": ppa,
        "price_per_acre_display": f"${ppa:,.0f}/ac" if ppa is not None else None,
        "land_type": (parcel.land_use if parcel else None) or "Land",
        "signal": score.signal.value if score and score.signal else None,
        "best_strategy": score.best_strategy.value if score and score.best_strategy else None,
        "risk": score.risk if score else None,
        "deep_link": f"/parcels/{match.parcel_id}",
        "opportunity_indicators": (score.why_interesting[:3] if score else []),
        "risk_indicators": (score.what_could_kill[:3] if score else []),
        "contact_website": website,
        "contact_phone": phone,
        "contact_office": source.get("office"),
        "find_parcel_url": find.get("url") if find else None,
        "find_parcel_label": (find.get("label") or "").replace("Find parcel ", "ID ") if find else None,
        "apn": parcel.apn if parcel else None,
        "links": links,
    }
