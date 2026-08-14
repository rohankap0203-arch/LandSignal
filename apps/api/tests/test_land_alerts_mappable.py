"""Land Alert mappable gate + notification summary honesty."""

from uuid import uuid4

from landsignal.models import LandAlertMatch, ListingRecord, ParcelRecord
from landsignal.services.land_alerts import (
    DEMO_USER_ID,
    _parcel_is_mappable,
    filter_mappable_matches,
    match_card,
)
from landsignal.store import MemoryStore


def _ring(lon: float, lat: float, pad: float = 0.01) -> list[list[list[float]]]:
    """Irregular closed ring — not an axis-aligned synthetic square."""
    return [
        [
            [lon - pad, lat - pad],
            [lon + pad * 1.2, lat - pad * 0.7],
            [lon + pad * 0.8, lat + pad],
            [lon - pad * 0.6, lat + pad * 0.9],
            [lon - pad, lat - pad],
        ]
    ]


def _square(lon: float, lat: float, pad: float = 0.01) -> list[list[list[float]]]:
    return [
        [
            [lon - pad, lat - pad],
            [lon + pad, lat - pad],
            [lon + pad, lat + pad],
            [lon - pad, lat + pad],
            [lon - pad, lat - pad],
        ]
    ]


def test_parcel_is_mappable_rejects_pin_only_and_synthetic():
    pin = ParcelRecord(latitude=35.1, longitude=-106.6, polygon=None, geometry_confidence=90)
    assert _parcel_is_mappable(pin) is False

    synth = ParcelRecord(
        latitude=35.1,
        longitude=-106.6,
        polygon=_square(-106.6, 35.1),
        geometry_confidence=70,
        is_demo=False,
    )
    assert _parcel_is_mappable(synth) is False

    real = ParcelRecord(
        latitude=35.1,
        longitude=-106.6,
        polygon=_ring(-106.6, 35.1),
        geometry_confidence=80,
        acreage=40,
        state="NM",
        is_demo=False,
    )
    assert _parcel_is_mappable(real) is True


def test_filter_mappable_matches_drops_unviewable():
    store = MemoryStore()
    good_id = uuid4()
    bad_id = uuid4()
    store.parcels[good_id] = ParcelRecord(
        id=good_id,
        latitude=35.1,
        longitude=-106.6,
        polygon=_ring(-106.6, 35.1),
        geometry_confidence=85,
        is_demo=False,
    )
    store.parcels[bad_id] = ParcelRecord(
        id=bad_id,
        latitude=35.2,
        longitude=-106.5,
        polygon=None,
        is_demo=False,
    )
    profile_id = uuid4()
    matches = [
        LandAlertMatch(
            profile_id=profile_id,
            user_id=DEMO_USER_ID,
            parcel_id=good_id,
            preference_match_pct=88,
            landsignal_score=72,
        ),
        LandAlertMatch(
            profile_id=profile_id,
            user_id=DEMO_USER_ID,
            parcel_id=bad_id,
            preference_match_pct=91,
            landsignal_score=80,
        ),
    ]
    kept = filter_mappable_matches(store, matches)
    assert len(kept) == 1
    assert kept[0].parcel_id == good_id


def test_match_card_omits_placeholder_price_and_sets_boundary_gate():
    store = MemoryStore()
    pid = uuid4()
    store.parcels[pid] = ParcelRecord(
        id=pid,
        latitude=40.0,
        longitude=-105.0,
        polygon=_ring(-105.0, 40.0),
        geometry_confidence=90,
        acreage=None,
        state="CO",
        is_demo=False,
    )
    store.listings[uuid4()] = ListingRecord(
        parcel_id=pid,
        provider_id="manual",
        external_id="x1",
        asking_price_usd=None,
        title="Quiet ridge",
    )
    match = LandAlertMatch(
        profile_id=uuid4(),
        user_id=DEMO_USER_ID,
        parcel_id=pid,
        preference_match_pct=80,
        landsignal_score=70,
    )
    card = match_card(store, match)
    assert card["asking_price_display"] is None
    assert card["acres_display"] is None
    assert card["has_boundary"] is True
