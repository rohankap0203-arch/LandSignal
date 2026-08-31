from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from landsignal.routers.api import router
from landsignal.settings import get_settings
from landsignal.store import get_store

settings = get_settings()

app = FastAPI(
    title="LandSignal API",
    version="0.1.0",
    description="Institutional land acquisition intelligence — screening only; no automated purchasing.",
)

app.add_middleware(GZipMiddleware, minimum_size=800)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix=settings.api_prefix)


@app.on_event("startup")
async def startup() -> None:
    import asyncio

    import structlog

    from landsignal.services.memory_guard import snapshot

    log = structlog.get_logger()
    log.info("startup_memory", **snapshot())

    store = get_store(settings.demo_seed)
    store.rebuild_listing_index()
    try:
        from landsignal.services.property_providers.pipeline import load_all_attom_snapshots

        reserved = len(load_all_attom_snapshots())
        log.info(
            "startup_inventory_memory",
            parcels=len(store.parcels),
            listings=len(store.listings),
            enrichments=len(store.enrichments),
            attom_reserved=reserved,
        )
    except Exception:
        pass
    try:
        from landsignal.services.land_gate import purge_non_land_from_store
        from landsignal.store import persist_store

        removed = purge_non_land_from_store(store)
        if removed:
            log.info("startup_purged_non_land", removed=removed)
            persist_store(store)
            log.info("startup_persisted_land_only_inventory")
    except Exception as exc:  # noqa: BLE001
        log.warning("startup_purge_non_land_failed", error=str(exc))
    # Promote assessor land marks → ask for every state (NJ/NY/MA/AR/WI/VT/TN/…).
    try:
        import structlog

        from landsignal.services.assessed_price import backfill_store_assessed_asks

        bf = backfill_store_assessed_asks(store)
        structlog.get_logger().info("startup_assessed_ask_backfill", **bf)
    except Exception as exc:  # noqa: BLE001
        import structlog

        structlog.get_logger().warning("startup_assessed_ask_backfill_failed", error=str(exc))
    # Default high-conviction alert rule
    if not store.alert_rules:
        from landsignal.services.alerts import create_rule

        create_rule(
            store,
            "High-conviction land signal",
            {
                "opportunity_gt": 70,
                "risk_lt": 45,
                "confidence_gt": 40,
                "asymmetry_gt": 60,
            },
            ["IN_APP", "EMAIL", "SMS"],
        )

    async def _bg_rescore() -> None:
        import structlog

        from landsignal.services.rescore import rescore_stale

        log = structlog.get_logger()
        try:
            # Keep startup light — large inventories used to pin CPU for minutes.
            summary = await rescore_stale(store, limit=500, concurrency=8)
            log.info("startup_rescore", **summary)
        except Exception as exc:  # noqa: BLE001
            log.warning("startup_rescore_failed", error=str(exc))

    asyncio.create_task(_bg_rescore())

    if settings.auto_discover_on_startup:
        from landsignal.services.discover import discover_opportunities

        async def _bg_discover() -> None:
            import structlog

            log = structlog.get_logger()
            try:
                summary = await discover_opportunities(
                    store,
                    settings,
                    limit=settings.discover_limit,
                    min_acres=settings.discover_min_acres,
                )
                log.info("startup_discover", **summary)
            except Exception as exc:  # noqa: BLE001
                log.warning("startup_discover_failed", error=str(exc))

        asyncio.create_task(_bg_discover())

    # Always-on Land Alerts monitor — runs even when no browser is open
    if settings.land_alerts_monitor_enabled:
        from landsignal.services.discover import discover_opportunities
        from landsignal.store import persist_store

        async def _land_alerts_monitor() -> None:
            import structlog

            log = structlog.get_logger()
            # Stagger first cycle so startup discover can finish
            await asyncio.sleep(max(60, min(300, settings.land_alerts_poll_seconds // 3)))
            failures = 0
            while True:
                try:
                    summary = await discover_opportunities(
                        store,
                        settings,
                        limit=settings.land_alerts_discover_limit,
                        min_acres=settings.discover_min_acres,
                        fast=True,
                    )
                    persist_store(store)
                    failures = 0
                    log.info("land_alerts_monitor_cycle", **{k: summary.get(k) for k in ("imported", "refreshed", "scored", "inventory_total", "errors")})
                except Exception as exc:  # noqa: BLE001
                    failures += 1
                    log.warning("land_alerts_monitor_failed", error=str(exc), failures=failures)
                # Back off on repeated failures without stopping the loop
                delay = settings.land_alerts_poll_seconds
                if failures:
                    delay = min(delay * (2 ** min(failures, 4)), delay * 8)
                await asyncio.sleep(delay)

        asyncio.create_task(_land_alerts_monitor())


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "service": "LandSignal API",
        "docs": "/docs",
        "health": f"{settings.api_prefix}/health",
    }
