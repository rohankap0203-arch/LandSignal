"""Durable inventory persist path prefers workspace over ephemeral /tmp."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from landsignal.models import ListingRecord, ParcelRecord
from landsignal.store import MemoryStore, load_persisted_store, persist_store


def test_persist_prefers_workspace_path(tmp_path, monkeypatch):
    dump = tmp_path / "landsignal_inventory.json"
    monkeypatch.setenv("LANDSIGNAL_INVENTORY_PATH", str(dump))
    import landsignal.store as store_mod

    monkeypatch.setattr(store_mod, "_PERSIST_PATH", str(dump))

    store = MemoryStore()
    pid = uuid4()
    lid = uuid4()
    store.parcels[pid] = ParcelRecord(
        id=pid,
        state="FL",
        county="Test",
        acreage=5.0,
        latitude=27.0,
        longitude=-81.0,
        is_demo=False,
    )
    store.listings[lid] = ListingRecord(
        id=lid,
        parcel_id=pid,
        provider_id="gis",
        external_id="fl-1",
        title="Test parcel",
        is_demo=False,
    )
    persist_store(store)
    assert dump.exists()
    assert dump.stat().st_size > 8
    payload = json.loads(dump.read_text())
    assert len(payload["parcels"]) == 1
    assert len(payload["listings"]) == 1

    restored = MemoryStore()
    n = load_persisted_store(restored)
    assert n == 1
    assert pid in restored.parcels


def test_load_falls_back_to_legacy_tmp(tmp_path, monkeypatch):
    legacy = tmp_path / "legacy.json"
    durable = tmp_path / "durable" / "landsignal_inventory.json"
    monkeypatch.setenv("LANDSIGNAL_INVENTORY_PATH", str(durable))
    import landsignal.store as store_mod

    monkeypatch.setattr(store_mod, "_PERSIST_PATH", str(durable))
    monkeypatch.setattr(
        store_mod,
        "_LEGACY_PERSIST_PATHS",
        (str(legacy), str(durable)),
    )

    pid = uuid4()
    legacy.write_text(
        json.dumps(
            {
                "parcels": [
                    {
                        "id": str(pid),
                        "state": "TX",
                        "county": "Test",
                        "acreage": 2.0,
                        "latitude": 31.0,
                        "longitude": -99.0,
                        "is_demo": False,
                    }
                ],
                "listings": [],
                "scores": {},
            }
        ),
        encoding="utf-8",
    )
    store = MemoryStore()
    n = load_persisted_store(store)
    assert n == 1
    assert pid in store.parcels
