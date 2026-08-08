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
    get_store(settings.demo_seed)


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "service": "LandSignal API",
        "docs": "/docs",
        "health": f"{settings.api_prefix}/health",
    }
