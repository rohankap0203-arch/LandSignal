from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from landsignal.routers.api import router
from landsignal.settings import get_settings
from landsignal.store import get_store

settings = get_settings()

app = FastAPI(
    title="LandSignal API",
    version="0.1.0",
    description="Institutional land acquisition intelligence — screening only; no automated purchasing.",
)

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
    store = get_store(settings.demo_seed)
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
    if settings.auto_discover_on_startup:
        import asyncio

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


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "service": "LandSignal API",
        "docs": "/docs",
        "health": f"{settings.api_prefix}/health",
    }
