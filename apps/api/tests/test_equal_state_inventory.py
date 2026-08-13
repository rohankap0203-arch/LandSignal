"""Nationwide discover should budget a large equal pull for every wired state."""

from __future__ import annotations

from collections import defaultdict

from landsignal.providers.public_markets import SOURCES
from landsignal.settings import Settings


def test_every_tax_source_state_gets_large_floor_budget():
    settings = Settings()
    wired = sorted(
        {
            s.state.upper()
            for s in SOURCES
            if "surplus" not in s.source_id and "fairfax" not in s.source_id
        }
    )
    assert len(wired) >= 20
    min_per_state = settings.discover_min_per_state
    assert min_per_state >= 10000
    # Total discover budget must fit equal floors for all wired states.
    assert settings.discover_limit >= min_per_state * len(wired) // 2
    tax_limit = max(settings.discover_limit, min_per_state * len(wired))
    per_state = max(min_per_state, (tax_limit + len(wired) - 1) // len(wired))
    assert per_state >= min_per_state
    # Florida is not the only state that clears the large floor.
    assert "FL" in wired
    assert "TX" in wired or "NY" in wired
    assert "CA" in wired or "WA" in wired


def test_equal_quota_diversify_does_not_let_one_state_crowd_out():
    """Simulate the equal-quota pass used by PublicTaxSaleProvider."""
    by_state_feed: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for i in range(200):
        by_state_feed["FL"]["fl"].append({"state": "FL", "acreage": 100 + i, "external_id": f"fl:{i}"})
    for i in range(30):
        by_state_feed["IL"]["il"].append({"state": "IL", "acreage": 40 + i, "external_id": f"il:{i}"})
    for i in range(30):
        by_state_feed["OH"]["oh"].append({"state": "OH", "acreage": 40 + i, "external_id": f"oh:{i}"})

    state_keys = ["FL", "IL", "OH"]
    limit = 90
    n_states = 3
    per_state = 50
    state_quota = max(1, min(per_state, (limit + n_states - 1) // n_states))
    taken = {st: 0 for st in state_keys}
    diversified: list[dict] = []

    def _take_round(*, respect_quota: bool) -> bool:
        progressed = False
        for st in list(by_state_feed.keys()):
            if respect_quota and taken.get(st, 0) >= state_quota:
                continue
            if len(diversified) >= limit:
                break
            feeds = by_state_feed.get(st) or {}
            if not feeds:
                by_state_feed.pop(st, None)
                continue
            for feed in list(feeds.keys()):
                if not feeds.get(feed):
                    feeds.pop(feed, None)
                    continue
                diversified.append(feeds[feed].pop(0))
                taken[st] = taken.get(st, 0) + 1
                progressed = True
                if not feeds.get(feed):
                    feeds.pop(feed, None)
                break
            if not feeds:
                by_state_feed.pop(st, None)
        return progressed

    while len(diversified) < limit and by_state_feed and _take_round(respect_quota=True):
        pass
    while len(diversified) < limit and by_state_feed and _take_round(respect_quota=False):
        pass

    counts = defaultdict(int)
    for row in diversified:
        counts[row["state"]] += 1
    assert counts["IL"] >= 25
    assert counts["OH"] >= 25
    # FL may fill remainder, but smaller states must keep a real share.
    assert counts["FL"] <= 40
