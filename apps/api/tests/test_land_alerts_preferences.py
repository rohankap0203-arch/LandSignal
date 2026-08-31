"""Strict Land Alert preference scoring — don't waste the buyer's time."""

from uuid import uuid4

from landsignal.models import (
    LandAlertNotify,
    LandAlertProfile,
    ListingRecord,
    ParcelRecord,
    ScoreRecord,
    Signal,
    Strategy,
)
from landsignal.services.land_alerts import score_parcel_against_profile
from landsignal.store import MemoryStore


def _ring(lon: float, lat: float, pad: float = 0.01) -> list[list[list[float]]]:
    return [
        [
            [lon - pad, lat - pad],
            [lon + pad * 1.2, lat - pad * 0.7],
            [lon + pad * 0.8, lat + pad],
            [lon - pad * 0.6, lat + pad * 0.9],
            [lon - pad, lat - pad],
        ]
    ]


def _parcel(state: str = "FL", acres: float = 20.0, land_use: str = "Vacant agricultural land") -> ParcelRecord:
    pid = uuid4()
    return ParcelRecord(
        id=pid,
        state=state,
        county="Test",
        acreage=acres,
        latitude=28.0,
        longitude=-81.5,
        polygon=_ring(-81.5, 28.0),
        geometry_confidence=85,
        land_use=land_use,
        is_demo=False,
    )


def _listing(parcel_id, ask: float | None) -> ListingRecord:
    return ListingRecord(
        parcel_id=parcel_id,
        provider_id="test",
        external_id=str(uuid4()),
        asking_price_usd=ask,
        status="active",
        title="Test tract",
        is_demo=False,
    )


def _score(
    parcel_id,
    opportunity: float = 70.0,
    risk: float = 40.0,
    strategy: Strategy = Strategy.FARMLAND,
) -> ScoreRecord:
    return ScoreRecord(
        parcel_id=parcel_id,
        algorithm_version="test",
        weight_version="test",
        opportunity=opportunity,
        risk=risk,
        confidence=70.0,
        asymmetry=10.0,
        signal=Signal.WATCH,
        best_strategy=strategy,
        deal_readiness=55.0,
        strategy_scores={strategy.value: 80.0},
        input_hash=f"test-{parcel_id}",
    )


def _seed(store: MemoryStore, parcel: ParcelRecord, ask: float | None, opportunity: float = 70.0, risk: float = 40.0):
    listing = _listing(parcel.id, ask)
    store.parcels[parcel.id] = parcel
    store.listings[listing.id] = listing
    store.index_listing(listing)
    store.scores[parcel.id] = [_score(parcel.id, opportunity=opportunity, risk=risk)]


def _profile(**prefs) -> LandAlertProfile:
    return LandAlertProfile(
        user_id=uuid4(),
        name="Strict test",
        preferences=prefs,
        notify=LandAlertNotify(sensitivity="strong"),
    )


def test_must_state_rejects_out_of_state():
    store = MemoryStore()
    parcel = _parcel(state="TX", acres=25)
    _seed(store, parcel, 120_000, opportunity=75)
    profile = _profile(states=["FL"], states_mode="must", budget_max=200000, budget_mode="prefer")
    result = score_parcel_against_profile(store, parcel, profile)
    assert result["hard_fail"] is True
    assert result["qualifies"] is False


def test_prefer_state_also_rejects_out_of_state():
    store = MemoryStore()
    parcel = _parcel(state="GA", acres=25)  # SE neighbor of FL — still not selected
    _seed(store, parcel, 120_000, opportunity=80)
    profile = _profile(
        states=["FL"],
        states_mode="prefer",
        budget_max=200000,
        budget_mode="prefer",
        acres_min=10,
        acres_max=40,
    )
    result = score_parcel_against_profile(store, parcel, profile)
    assert result["hard_fail"] is True
    assert result["qualifies"] is False


def test_prefer_budget_rejects_far_over_max():
    store = MemoryStore()
    parcel = _parcel(state="FL", acres=20)
    _seed(store, parcel, 400_000, opportunity=80)
    profile = _profile(
        states=["FL"],
        states_mode="must",
        budget_max=150000,
        budget_mode="prefer",
        acres_min=10,
        acres_max=40,
        acres_mode="prefer",
    )
    result = score_parcel_against_profile(store, parcel, profile)
    assert result["hard_fail"] is True
    assert result["qualifies"] is False


def test_unpriced_fails_when_budget_constrained():
    store = MemoryStore()
    parcel = _parcel(state="FL", acres=20)
    _seed(store, parcel, None, opportunity=80)
    profile = _profile(
        states=["FL"],
        states_mode="must",
        budget_max=200000,
        budget_mode="prefer",
    )
    result = score_parcel_against_profile(store, parcel, profile)
    assert result["hard_fail"] is True
    assert result["qualifies"] is False


def test_must_acres_rejects_outside_band():
    store = MemoryStore()
    parcel = _parcel(state="FL", acres=3)
    _seed(store, parcel, 50_000, opportunity=80)
    profile = _profile(
        states=["FL"],
        states_mode="must",
        budget_max=200000,
        budget_mode="prefer",
        acres_min=10,
        acres_max=40,
        acres_mode="must",
    )
    result = score_parcel_against_profile(store, parcel, profile)
    assert result["hard_fail"] is True
    assert result["qualifies"] is False


def test_land_type_mismatch_hard_fails():
    store = MemoryStore()
    parcel = _parcel(state="FL", acres=22, land_use="Commercial retail pad")
    _seed(store, parcel, 95_000, opportunity=80)
    profile = _profile(
        states=["FL"],
        states_mode="must",
        budget_max=150000,
        budget_mode="prefer",
        land_types=["agricultural", "farmland"],
    )
    result = score_parcel_against_profile(store, parcel, profile)
    assert result["hard_fail"] is True
    assert result["qualifies"] is False


def test_in_band_strong_fit_qualifies():
    store = MemoryStore()
    parcel = _parcel(state="FL", acres=22)
    _seed(store, parcel, 95_000, opportunity=72, risk=40)
    profile = _profile(
        states=["FL"],
        states_mode="must",
        budget_max=150000,
        budget_mode="prefer",
        acres_min=10,
        acres_max=40,
        acres_mode="prefer",
        max_risk="moderate",
    )
    result = score_parcel_against_profile(store, parcel, profile)
    assert result["hard_fail"] is False
    assert result["preference_match_pct"] >= 75
    assert result["qualifies"] is True


def test_risk_over_comfort_hard_fails():
    store = MemoryStore()
    parcel = _parcel(state="FL", acres=22)
    _seed(store, parcel, 95_000, opportunity=80, risk=70)
    profile = _profile(
        states=["FL"],
        states_mode="must",
        budget_max=150000,
        budget_mode="prefer",
        max_risk="moderate",  # cap 55
    )
    result = score_parcel_against_profile(store, parcel, profile)
    assert result["hard_fail"] is True
    assert result["qualifies"] is False


def test_strategy_mismatch_hard_fails():
    store = MemoryStore()
    parcel = _parcel(state="FL", acres=22)
    listing = _listing(parcel.id, 95_000)
    store.parcels[parcel.id] = parcel
    store.listings[listing.id] = listing
    store.index_listing(listing)
    store.scores[parcel.id] = [
        _score(parcel.id, opportunity=80, risk=40, strategy=Strategy.ENERGY)
    ]
    profile = _profile(
        states=["FL"],
        states_mode="must",
        budget_max=150000,
        budget_mode="prefer",
        strategies=["farmland", "agricultural"],
    )
    result = score_parcel_against_profile(store, parcel, profile)
    assert result["hard_fail"] is True
    assert result["qualifies"] is False
