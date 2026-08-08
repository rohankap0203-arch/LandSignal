# LandSignal — Frontend Information Architecture

## Aesthetic

Institutional terminal: dense, calm, precise. Dark default + light mode. Bloomberg/Palantir clarity without cartoon signals. No marketing-hero layout.

## Primary surfaces (Phase 1)

### 1. Opportunity Radar (`/`)
- Top toolbar: filters (score, risk, confidence, acres, price, strategy, state)
- Table columns: Signal, Property, Location, Acres, Ask, $/Acre, Est. Value, Discount, LandSignal, Asymmetry, Risk, Confidence, Best Strategy, Freshness, Status
- Row click → Property Intelligence
- Provider status strip: each integration CONFIGURED / NOT_CONFIGURED

### 2. Map Mode (`/map`)
- USA → state → county → parcel
- Heat layers: opportunity, mispricing, farmland, development, growth (stubs if data thin)
- Mapbox when `NEXT_PUBLIC_MAPBOX_TOKEN` set; else structured NOT_CONFIGURED panel + list fallback

### 3. Property Intelligence (`/parcels/[id]`)
Sections in order:
1. Executive summary scores  
2. Why interesting / mispriced / kill / still available / verify  
3. Map overlays  
4. Financials & scenarios  
5. Land / soils / flood / wetlands / topography  
6. Zoning / utilities (UNKNOWN when absent)  
7. Agriculture  
8. Comps  
9. Ownership / listing history  
10. Catalysts / risks  
11. Sources & provenance  
12. Manual DD checklist + Deal Readiness  

Actions: Watch, Create Alert, Generate Memo

### 4. Alerts (`/alerts`)
Rule builder + delivery channel status (email/SMS NOT_CONFIGURED without secrets)

### 5. Ingest (`/ingest`)
CSV upload, manual parcel entry, provider status

### 6. Investor Profile (`/profile`)
Capital, acres, price, IRR, strategies, risk tolerance → Personalized Score (separate column when enabled)

## Component rules

- Small focused components  
- ProvenanceHint on material facts  
- KnowledgeStateBadge for KNOWN/UNKNOWN/ESTIMATED/…  
- No fake Mapbox tiles without token  
