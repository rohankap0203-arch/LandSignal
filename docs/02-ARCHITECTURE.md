# LandSignal — Architecture Plan

## System purpose

Discover parcels where **risk-adjusted economic value appears materially greater than the achievable purchase price**, with evidence strong enough to justify immediate human diligence — not to auto-buy land.

## High-level architecture

```
┌─────────────┐   ┌──────────────┐   ┌────────────────┐
│  Next.js UI │──▶│  FastAPI API │──▶│ PostgreSQL+GIS │
│  Radar/Map  │   │  REST/WS     │   │  Redis queues  │
└─────────────┘   └──────┬───────┘   └───────▲────────┘
                         │                   │
              ┌──────────▼──────────┐        │
              │  Job Orchestrator   │────────┤
              │  (Redis + workers)  │        │
              └──────────┬──────────┘        │
     ┌───────────────────┼───────────────────┐
     ▼                   ▼                   ▼
 Listing adapters   Gov geospatial      Scoring engine
 (MLS/Land/CSV)     (SSURGO/FEMA/NWI)   (versioned TS/Py)
```

## Repository layout

```
apps/web          Next.js + Tailwind + shadcn (Opportunity Radar, Property IQ)
apps/api          FastAPI control plane (ingestion, scores, alerts, memos)
services/workers  Python analysis workers (geospatial, economics, catalysts)
packages/shared   Shared TypeScript types / OpenAPI client stubs
packages/scoring  Versioned explainable scoring (unit-tested)
database/         SQL migrations (PostGIS)
integrations/     Provider adapter contracts + implementations
docs/             Architecture, APIs, phases, risks
```

## Core domains

1. **Ingestion** — ListingProvider adapters, change detection, dead-letter  
2. **Identity** — listing ↔ parcel resolution with confidence  
3. **Digital Twin** — canonical parcel + provenance-wrapped attributes  
4. **Screening** — strategy-scoped PASS / FAIL / MANUAL_REVIEW  
5. **Geospatial** — polygon overlays, distances, buildable acreage  
6. **Economics** — ag / development / energy scenarios (base/bull/bear)  
7. **Scoring** — global + personalized + strategy scores, asymmetry, risk, confidence  
8. **Surveillance** — alerts, watchlists, freshness/urgency  
9. **Decision support** — memos, DD checklists, deal readiness  
10. **Calibration** — backtests, weight configs, audit logs (Phase 2+)

## API surface (Phase 1)

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness + dependency status |
| GET | `/v1/providers` | Provider config status |
| POST | `/v1/ingest/csv` | CSV listing import |
| POST | `/v1/ingest/manual` | Manual parcel/listing |
| POST | `/v1/parcels/{id}/analyze` | Enqueue analysis pipeline |
| GET | `/v1/radar` | Opportunity Radar rows |
| GET | `/v1/parcels/{id}` | Property intelligence payload |
| GET | `/v1/parcels/{id}/scores` | Score breakdown + audit |
| POST | `/v1/alerts/rules` | Create alert rule |
| GET | `/v1/alerts` | Alert history |
| POST | `/v1/parcels/{id}/memo` | Generate deal memo |
| GET | `/v1/investor-profile` | Profile for personalized score |

## Analysis pipeline (sequential stages)

1. `normalize_listing`  
2. `resolve_parcel_geometry`  
3. `stage1_kill_screens` (per strategy)  
4. `soil_analysis` / `flood_analysis` / `wetlands_analysis` / `terrain_analysis`  
5. `access_heuristic` (not legal verification)  
6. `comps_assemble`  
7. `score_v1`  
8. `why_unsold` / `hidden_value` heuristics  
9. `alert_evaluate`  

Failures in one enrichment step mark attribute status `UNKNOWN` / `DATA_TEMPORARILY_UNAVAILABLE` and reduce confidence — they do not crash the pipeline.

## Scoring architecture

See `packages/scoring` and `docs/04-SCORING.md`.

- Algorithm version: `landsignal_score_v1`  
- Weights loaded from DB/config, not hard-coded constants in UI  
- Outputs: opportunity, risk, confidence, asymmetry, strategy scores, best/secondary strategy  
- Every run writes `score_components` + input snapshot hash for reproducibility  

## Auth & tenancy (Phase 1 stub)

Single-tenant local mode. JWT/auth provider deferred; API assumes local trusted user. Multi-tenant RLS planned in schema (`org_id` columns).

## Observability

Structured JSON logs; every score includes `algorithm_version`, `weight_version`, `input_hash`, `computed_at`.

## Non-goals (Phase 1)

- Automated offers / wiring funds  
- Opaque ML-only recommendations  
- Scraping sites against ToS  
- Pretending unconfigured commercial APIs are live  
