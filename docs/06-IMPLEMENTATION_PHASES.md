# LandSignal — Implementation Phases

## Phase 1 — Vertical slice (this delivery)
- Monorepo + Docker Compose (Postgres/PostGIS, Redis, API, web, worker)
- Schema + migrations
- ListingProvider interface + Manual/CSV + stubs (NOT_CONFIGURED)
- Parcel digital twin normalization
- Public adapters: SSURGO, FEMA NFHL, NWI, USGS elevation
- Fast rejection (strategy-scoped)
- Scoring v1 + audit log
- Opportunity Radar + Property Intelligence
- Alert rules engine (in-app; email/SMS NOT_CONFIGURED without creds)
- Deal memo generator (markdown)
- Tests: scoring, geospatial math, financial helpers
- Docs: critique, architecture, sources, scoring, IA, risks

## Phase 2 — Market depth
- Paid parcel vendor adapter
- Closed comps pipeline + adjustments UI
- Path-of-growth v1 (permits + population)
- Farmland economics scenarios
- Watchlists + listing psychology timelines
- Backtesting harness (walk-forward)

## Phase 3 — Optionality engines
- Development optionality
- Solar/wind/energy infrastructure scores (HIFLD + zoning)
- Assemblage engine
- Catalyst ingestion
- Why-unsold / hidden-value upgrades

## Phase 4 — Portfolio & ML
- Portfolio mode
- Personalized ranking at scale
- Explainable ML (GBDT) beside rules
- Weight optimization from outcomes
- Multi-tenant auth

## Definition of done (Phase 1)
- `docker compose up` boots stack **or** local API+web against compose DB
- Can ingest CSV → analyze → see radar row → open intelligence page
- Unconfigured providers show NOT_CONFIGURED
- Tests pass for scoring/geospatial/financial modules
