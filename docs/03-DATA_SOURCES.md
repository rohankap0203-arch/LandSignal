# LandSignal — Data Sources & Integrations

## Adapter contract

Every listing source implements:

```ts
interface ListingProvider {
  id: string;
  status(): ProviderStatus; // CONFIGURED | NOT_CONFIGURED | DEGRADED | ERROR
  searchListings(query: SearchQuery): Promise<ProviderResult<RawListing[]>>;
  getListing(externalId: string): Promise<ProviderResult<RawListing>>;
  normalizeListing(raw: RawListing): NormalizedListing;
  detectChanges(prev: NormalizedListing, next: NormalizedListing): ListingChange[];
}
```

Every government/enrichment source implements:

```ts
interface EnrichmentProvider<T> {
  id: string;
  status(): ProviderStatus;
  enrich(parcel: ParcelRef): Promise<ProviderResult<Provenanced<T>>>;
}
```

`Provenanced<T>` always includes: `source`, `retrieved_at`, `effective_date`, `confidence`, `geographic_resolution`, `raw`, `normalized`, `knowledge_state` (`KNOWN|UNKNOWN|ESTIMATED|NOT_APPLICABLE`).

---

## Listing / market sources

| Source | Phase 1 | Access | Notes |
|---|---|---|---|
| Manual parcel / URL entry | **Implemented** | Free | Always available |
| CSV import | **Implemented** | Free | Broker exports, internal sheets |
| Demo fixtures | Dev-only | Free | Labeled `DEMO`; never shown as live feed |
| BLM LPAD | **Implemented** | Free | Federal western disposal tracts |
| County tax-sale / land-bank GIS | **Implemented** | Free | Spot counties nationwide |
| Municipal / TxDOT surplus GIS | **Implemented** | Free | Surplus / excess land |
| Statewide vacant/ag cadastral screens | **Implemented** | Free | 50-state ArcGIS vacant/ag layers |
| Extra free vacant feeds | **Implemented** | Free | CT vacant CAMA, LA County vacant, Broward vacant, Rochester vacant, Cuyahoga vacant, ASLD trust |
| RESO/MLS web API | Stub | **Paid / licensed** via MLS/board or aggregator | Homes-heavy; land thin |
| Land.com / LandWatch / LandAndFarm | Stub | **Paid / partnership** | Best for **active land-for-sale** |
| ATTOM property API | Stub | **Paid / 30-day trial** | Nationwide parcel attributes, not a land marketplace |
| Crexi / LoopNet | Stub | **Paid API / license** | Commercial / development land |
| Broker feeds | Stub | Contractual | Per-broker CSV/SFTP |

If credentials missing → API returns `status: NOT_CONFIGURED` (never synthetic listings from that provider).

### How to acquire land-only (not homes) marketplace data

1. **Land.com family (best product fit)**  
   - Contact Landmark Interactive / Land.com partnerships or API sales (not a public self-serve free API).  
   - Tell them you need **acreage / vacant / farm / ranch / recreational land listings**, nationwide or multi-state, with price + acres + geo.  
   - Env once licensed: `LAND_COM_API_KEY`.

2. **ATTOM (best free-trial backbone)**  
   - Sign up: https://api.developer.attomdata.com/signup → 30-day trial key under Account → Applications.  
   - Use for APN / assessments / property characteristics nationwide.  
   - Env: `ATTOM_API_KEY` (adapter still pending full ingest).

3. **Crexi** — commercial & development sites via partner API (`CREXI_API_KEY`).

4. **MLS / Bridge / RESO** — only if you have a broker + IDX agreements; mostly houses, sparse land.

5. **Do not scrape** Land.com / Zillow / Redfin / MLS sites — violates terms and is not a durable inventory path.

### Free path (what LandSignal runs today)

Refresh live inventory pulls BLM + public tax/surplus + statewide vacant GIS + the extra free feeds above. These are **cadastral / surplus screens**, not guaranteed active asking-price land listings.

---

## Public / government datasets

| Dataset | Use | National? | Access | Phase 1 |
|---|---|---|---|---|
| USDA NRCS SSURGO / SDA | Soils, farmland class, AWC | Yes | Free (SDA SOAP/REST) | Adapter implemented |
| USDA CDL | Crop history | Yes | Free (CroplandCROS / GEE) | Interface + stub if heavy |
| NCCPI | Productivity | Via SSURGO | Free | When present in soil attrs |
| FEMA NFHL | Flood zones | Yes | Free MapServer/WMS | Adapter implemented |
| USFWS NWI | Wetlands | Yes | Free MapServer | Adapter implemented |
| USGS 3DEP / EPQS | Elevation/slope | Yes | Free | Adapter implemented |
| Census TIGER | Roads, boundaries | Yes | Free | Distance helpers |
| Census ACS / permits | Demographics, growth | Yes | Free | Phase 2 |
| EPA Envirofacts / SEMS / Brownfields | Env hazards | Yes | Free | Phase 2 |
| Opportunity Zones | Tax overlay | Yes | Free | Phase 2 |
| USGS / drought / climate | Risk | Yes | Free | Phase 2 |
| County parcel/assessor/zoning | Twin core | **No — county-by-county** | Mixed | Manual + stubs |
| State water rights | Water value | **No** | Mixed | NOT_APPLICABLE / UNKNOWN |
| Utility / transmission GIS | Energy | Partial (HIFLD) | HIFLD free; utility internals paid/private | HIFLD optional Phase 1.5 |
| Regrid / LightBox / ATTOM | Parcels+comps | Near-national | **Paid** | Stub |
| CoreLogic / First American | Title/comps | Near-national | **Paid** | Stub |

---

## What cannot be obtained reliably nationwide

1. Homogeneous zoning / future land use  
2. Recorded access easements as structured data  
3. True closed land comps with clean arms-length flags  
4. Water rights geospatial completeness  
5. Sewer/water main locations  
6. Interconnection capacity  
7. Beneficial ownership behind LLCs  
8. Septic/perc results  
9. Mineral ownership severance completeness  
10. Authoritative national parcel polygons without a paid vendor  

---

## Paid / licensed (must configure)

- MLS / RESO access  
- Land.com family APIs (if offered)  
- Crexi / LoopNet  
- Regrid / LightBox / ATTOM / CoreLogic parcel+comp stacks  
- Mapbox (token required for map tiles; UI shows NOT_CONFIGURED map fallback without token)  
- Twilio (SMS alerts)  
- SendGrid/SES (email alerts)  

Env vars documented in `.env.example`. Missing secrets ⇒ `NOT_CONFIGURED`.

---

## Rate limits / resilience

All external calls: timeouts, exponential backoff, circuit breaker, response cache, DLQ.  
Enrichment failures set knowledge_state and reduce Data Confidence; pipeline continues.
