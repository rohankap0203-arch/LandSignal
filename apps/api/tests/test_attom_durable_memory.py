"""Durable ATTOM / inventory memory — key expiry must not erase presented data."""

from __future__ import annotations

from uuid import uuid4

import pytest

from landsignal.models import EnrichmentBundle, KnowledgeState, ParcelRecord, Provenanced
from landsignal.services.property_providers.pipeline import (
    attom_fields_to_enrichment_patch,
    hydrate_attom_memory_into_store,
    load_attom_snapshot,
    prior_attom_ok,
    snapshot_attom_enrichment,
)
from landsignal.store import MemoryStore


@pytest.fixture()
def attom_memory_path(tmp_path, monkeypatch):
    path = tmp_path / "attom_memory.json"
    monkeypatch.setenv("LANDSIGNAL_ATTOM_MEMORY_PATH", str(path))
    # Reload path constant used by pipeline module
    import landsignal.services.property_providers.pipeline as pipe

    monkeypatch.setattr(pipe, "_ATTOM_SNAPSHOT_PATH", str(path))
    return path


def test_snapshot_survives_and_merges(attom_memory_path):
    pid = str(uuid4())
    snapshot_attom_enrichment(
        parcel_key=pid,
        fields={"acreage": {"value": 12.5}, "attomId": 99},
        meta={"apn": "A-1"},
    )
    snapshot_attom_enrichment(
        parcel_key=pid,
        fields={"valuation": {"avmValue": {"value": 180000}}, "attomId": 99},
        meta={"apn": "A-1"},
    )
    entry = load_attom_snapshot(pid)
    assert entry is not None
    assert entry["fields"]["acreage"]["value"] == 12.5
    assert entry["fields"]["valuation"]["avmValue"]["value"] == 180000
    assert entry["persistencePolicy"] == "RESERVED_LAST_KNOWN"


def test_prior_attom_ok_detects_success():
    other = Provenanced(
        value={"attom": {"ok": True, "fields": {"acreage": {"value": 3}}}},
        knowledge_state=KnowledgeState.KNOWN,
        source="ATTOM",
    )
    assert prior_attom_ok(other) is not None
    fail = Provenanced(
        value={"attom": {"ok": False, "error": "expired"}},
        knowledge_state=KnowledgeState.TEMPORARILY_UNAVAILABLE,
        source="ATTOM",
    )
    assert prior_attom_ok(fail) is None


@pytest.mark.asyncio
async def test_enrich_falls_back_to_memory_when_live_fails(attom_memory_path, monkeypatch):
    pid = str(uuid4())
    snapshot_attom_enrichment(
        parcel_key=pid,
        fields={
            "acreage": {"value": 40.0},
            "marketStatus": "off_market",
            "hasStructure": False,
        },
    )

    class BoomProvider:
        def __init__(self, settings=None):
            pass

        async def enrich_parcel(self, *_a, **_k):
            return {"ok": False, "state": "TRIAL_EXPIRED", "fields": {}, "error": "trial expired"}

    import landsignal.services.property_providers.pipeline as pipe

    monkeypatch.setattr(pipe, "AttomPropertyProvider", BoomProvider)

    res = await pipe.enrich_with_attom(
        {"state": "FL", "acreage": None},
        deep=True,
        parcel_key=pid,
    )
    assert res["ok"] is True
    assert res["from_memory"] is True
    assert res["state"] == "RESERVED_MEMORY"
    assert res["fields"]["acreage"]["value"] == 40.0
    patch = attom_fields_to_enrichment_patch(res["fields"])
    assert patch["attom_acreage"] == 40.0


def test_hydrate_into_store_restores_enrichment(attom_memory_path):
    store = MemoryStore()
    pid = uuid4()
    store.parcels[pid] = ParcelRecord(
        id=pid,
        state="FL",
        latitude=28.0,
        longitude=-81.5,
        acreage=10,
        is_demo=False,
    )
    snapshot_attom_enrichment(
        parcel_key=str(pid),
        fields={"acreage": {"value": 10.0}, "attomId": 7, "hasStructure": False},
        meta={"data_confidence": 0.9},
    )
    n = hydrate_attom_memory_into_store(store)
    assert n == 1
    bundle = store.enrichments[pid]
    attom = prior_attom_ok(bundle.other)
    assert attom is not None
    assert attom["from_memory"] is True
    assert attom["fields"]["attomId"] == 7


def test_hydrate_does_not_clobber_live_success(attom_memory_path):
    store = MemoryStore()
    pid = uuid4()
    store.parcels[pid] = ParcelRecord(id=pid, state="FL", latitude=28.0, longitude=-81.5)
    store.enrichments[pid] = EnrichmentBundle(
        other=Provenanced(
            value={"attom": {"ok": True, "fields": {"attomId": 1, "live": True}}},
            knowledge_state=KnowledgeState.KNOWN,
            source="ATTOM",
        )
    )
    snapshot_attom_enrichment(
        parcel_key=str(pid),
        fields={"attomId": 999, "from_disk": True},
    )
    hydrate_attom_memory_into_store(store)
    assert store.enrichments[pid].other.value["attom"]["fields"]["attomId"] == 1
