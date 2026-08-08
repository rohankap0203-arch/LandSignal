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
| RESO/MLS web API | Stub | **Paid / licensed** via MLS/board or aggregator | Highly regional |
| Land.com / LandWatch / LandAndFarm | Stub | **Paid / partnership** | No unauthorized scraping |
| Crexi / LoopNet | Stub | **Paid API / license** | More CRE than ag |
| Broker feeds | Stub | Contractual | Per-broker CSV/SFTP |
| Auction platforms | Stub | Mixed | Terms vary |
| County tax-sale feeds | Stub | Often public, nonstandard | High defect rate |

If credentials missing → API returns `status: NOT_CONFIGURED` (never synthetic listings from that provider).

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
