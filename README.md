# LandSignal

Institutional-grade nationwide land acquisition intelligence platform.

**Objective:** find parcels whose risk-adjusted economic value appears materially greater than the price the market is asking — with evidence strong enough to justify immediate human diligence.

This software **never executes purchases**.

## Spec critique & architecture

Read before extending:

1. [`docs/01-SPEC_CRITIQUE.md`](docs/01-SPEC_CRITIQUE.md) — wrong assumptions, false positives, empiricism
2. [`docs/02-ARCHITECTURE.md`](docs/02-ARCHITECTURE.md)
3. [`docs/03-DATA_SOURCES.md`](docs/03-DATA_SOURCES.md) — paid vs free, national gaps
4. [`docs/04-SCORING.md`](docs/04-SCORING.md)
5. [`docs/05-FRONTEND_IA.md`](docs/05-FRONTEND_IA.md)
6. [`docs/06-IMPLEMENTATION_PHASES.md`](docs/06-IMPLEMENTATION_PHASES.md)
7. [`docs/07-RISKS_AND_ASSUMPTIONS.md`](docs/07-RISKS_AND_ASSUMPTIONS.md)

## Phase 1 vertical slice

Ingest → parcel twin → soils/flood/wetlands/terrain enrichment → scoring → Opportunity Radar → Property Intelligence → alerts → deal memo.

Unconfigured commercial integrations return **`NOT_CONFIGURED`** (never fake live feeds).  
Demo fixtures are labeled **`DEMO`** for UI walkthrough only.

## Stack

| Layer | Tech |
|---|---|
| Web | Next.js, TypeScript, Tailwind |
| API | FastAPI |
| Scoring | Versioned pure functions (`landsignal_score_v1`) in TS + Python |
| DB | PostgreSQL + PostGIS (schema in `database/migrations`) |
| Queue | Redis (wired; memory store default for Phase 1 local) |
| Maps | Mapbox when token present |

## Quick start (local, no Docker)

```bash
# API
cd apps/api
python3 -m venv .venv
source .venv/bin/activate
pip install fastapi uvicorn pydantic pydantic-settings httpx python-multipart \
  sqlalchemy asyncpg geoalchemy2 shapely redis orjson structlog tenacity pytest pytest-asyncio
export PYTHONPATH=.
export DEMO_SEED=true
uvicorn landsignal.main:app --reload --port 8000

# Web (other terminal)
cd apps/web
npm install
export NEXT_PUBLIC_API_URL=http://127.0.0.1:8000/v1
npm run dev
```

Open http://localhost:3000

## Docker

```bash
cp .env.example .env
docker compose up --build
```

## Tests

```bash
# TypeScript scoring / geospatial / financial
cd packages/scoring && npm install && npm test

# Python scoring / geospatial / financial
cd apps/api && PYTHONPATH=. pytest -q
```

## Provider honesty rules

- Missing API credentials → status `NOT_CONFIGURED`
- Failed government call → attribute `TEMPORARILY_UNAVAILABLE`, confidence reduced
- Missing data → does **not** silently become zero quality
- Access confidence is **never** “legally verified” without documents

## Disclaimer

Screening intelligence only. Not an appraisal, survey, title opinion, wetland delineation, investment advisory service, or authorization to transact.
