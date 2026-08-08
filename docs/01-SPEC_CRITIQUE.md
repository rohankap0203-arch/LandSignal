# LandSignal — Specification Critique

This document challenges the product specification before implementation. The goal is not to shrink ambition, but to prevent building a system that looks intelligent while being systematically wrong.

---

## Assumptions that are wrong or dangerous

1. **Nationwide continuous discovery is not a data problem first — it is a rights/licensing problem.**  
   Authorized MLS, Land.com, Crexi, LoopNet, county tax sales, and broker feeds are fragmented, expensive, geographically uneven, and contractually constrained. Without licensed feeds, “nationwide continuous discovery” collapses to sparse public auctions + manual URL/CSV intake.

2. **Parcel identity is harder than listing identity.**  
   Listings often omit APN, misstate acreage, use approximate pins, or bundle multiple parcels. Matching listing → legal parcel is a core failure mode. Treating every listing as a clean parcel digital twin will create false confidence.

3. **Asking price is often not an actionable market quote.**  
   Land listings are frequently aspirational, stale, or broker-fishing. Institutional buyers underwrite to achievable transaction price, not list price. Mispricing vs ask is useful triage; mispricing vs achievable entry is the real signal.

4. **“Highest and best use” cannot be reduced to 25 independent strategy scores without interaction effects.**  
   Strategies compete for the same acreage, share constraints (access, wetlands, zoning), and have different capital, entitlement, and hold-period requirements. A parcel can score high for solar and subdivision only if mutually exclusive footprints are modeled.

5. **Cheap compute screening will over-reject unique optionality.**  
   Instant kill tests based on incomplete public GIS (especially wetlands, flood, access) will kill deals that field diligence would save — and pass deals that title/access kill later.

6. **Historical appreciation is weakly predictive for raw land.**  
   Thin markets, idiosyncratic buyers, entitlement lottery outcomes, and local politics dominate. Backtests on sparse land sales will overfit unless carefully stratified.

7. **Proximity to transmission ≠ interconnection value.**  
   The spec correctly notes this for solar; it must be enforced as a hard product rule. Queue position, hosting capacity, and curtailment dominate site quality in many markets.

8. **Institutional capital already screens many obvious opportunities.**  
   Edge is more likely in: parcel/listing mismatch, assemblage, incomplete marketing, recent local catalyst not yet in comps, awkward size bands, estate/tax situations, and markets with poor broker coverage — not in “pretty farmland near a city.”

---

## What institutional investors would add

| Capability | Why it matters |
|---|---|
| **Carry / hold-cost model** | Taxes, insurance, maintenance, debt service, opportunity cost dominate multi-year land banking IRR |
| **Capital stack & mandate fit** | Fund docs restrict strategy, leverage, geography, lot size, development risk |
| **Entitlement probability model** | Not just zoning text — political feasibility, opposition, utility will-serve realism |
| **Basis vs replacement cost** | Especially ag and timber: productive value vs speculative option value |
| **Exit channel mapping** | Who is the realistic next buyer? Farmer, developer, REIT, solar, 1031 buyer, municipality |
| **Local intelligence layer** | Broker notes, county staff comments, unpublished moratoria, septic suitability |
| **Title / survey defect taxonomy** | Access easements, mineral severances, boundary gaps, cemetery/encroachments |
| **Water security under climate stress** | Not only rights existence — seniority, curtailment history, aquifer decline |
| **Insurance / uninsurability** | Flood/wildfire can make financing or resale impossible |
| **Conflict checks & co-investment** | Family offices care about partner concentration and reputational risk |
| **Decision journal** | Every pass/invest decision logged for calibration |

---

## Important variables overlooked

- **Septic / perc suitability** (often the real residential constraint, not zoning alone)
- **Drainage district / assessment liabilities**
- **Special assessments, CID/TIF overlays, agricultural deferrals / rollback taxes**
- **Conservation easement enforceability and reserved rights**
- **Mineral / wind / solar lease overlays already encumbering fee**
- **HOA / road maintenance associations for rural tracts**
- **Hunting lease income & recreational liability**
- **Timber cruise quality vs satellite canopy proxies**
- **Soil compaction / prior industrial use not in Superfund**
- **Local anti-solar / anti-growth ordinances**
- **Wetlands jurisdictional status (WOTUS) uncertainty**
- **Listing-to-parcel geometry mismatch residual error**
- **Broker exclusivity / pocket listings** (off-market share is large in land)
- **1031 exchange timing pressure** (buyer pool pulses)
- **Property tax appeal optionality**
- **Assemblage holdout risk / ransom pricing**
- **Construction cost inflation** (makes finished-lot math obsolete quickly)

---

## Data bottlenecks that prevent accurate analysis

| Domain | Bottleneck |
|---|---|
| Parcel polygons + APN | No free national authoritative layer; Regrid/LightBox/ATTOM are paid; county coverage uneven |
| Closed land comps | Sparse; deed consideration often unreliable or $0/related-party; use codes messy |
| Zoning / FLU | Non-standardized across ~3,000 counties; PDFs still common |
| Legal access / easements | Requires recorded documents; GIS road adjacency ≠ legal access |
| Water rights | State systems diverge; many not geospatial or machine-readable |
| Utilities | Private utility GIS rarely public; “nearest main” often unknown |
| Interconnection | Utility hosting capacity / queue data incomplete or delayed |
| Ownership | LLCs obscure beneficial ownership; privacy laws limit enrichment |
| Flood/wetlands | National layers are screening-grade, not delineation-grade |
| Soils | SSURGO excellent for ag screening; weak for development geotech |
| Catalysts | No single structured national feed; news/permit scraping is noisy |

**Rule for the product:** degrade confidence aggressively when these are missing. Never impute zeros.

---

## What cannot reliably be automated

1. Legal access confirmation from deeds/easements  
2. Title quality / exception risk  
3. True wetland delineation / ordinary high water  
4. Entitlement political feasibility  
5. Seller psychology beyond observable listing mechanics  
6. Interconnection capacity and utility will-serve  
7. Mineral ownership completeness  
8. Survey-accurate acreage and encroachments  
9. Local informal land-use norms  
10. Final investment decision / purchase execution  

These belong in **manual DD checklist** and **Deal Readiness**, never in silent score penalties disguised as facts.

---

## What creates false positives

1. **Wrong parcel match** to a listing pin  
2. **Acreage inflation** in listing copy  
3. **Stale ask after market moved down** → looks “cheap” vs old comps  
4. **Related-party or non-arm’s-length comps** polluting valuation  
5. **Ignoring carry costs** → high asymmetry on paper, negative IRR in reality  
6. **Strategy double-counting** the same upside (dev + solar + subdivision)  
7. **Flood/wetland layers missing local LOMA / mitigation reality** (both directions)  
8. **Growth corridor heuristics** without infrastructure funding reality  
9. **“Hidden value” from bad photos** when the land is simply bad  
10. **High score / low confidence** treated like high score / high confidence  
11. **Tax-sale / auction inventory** with undisclosed defects  
12. **Looking cheap per acre because most acreage is unusable**

---

## Making scoring empirically defensible

### Design principles
1. **Versioned, pure functions** — same inputs ⇒ same outputs; score runs are audited.  
2. **Separate layers:** Facts → Derived metrics → Strategy screens → Valuation → Opportunity → Risk → Confidence.  
3. **No missing-as-zero.** Missing lowers confidence, not quality, unless a kill-test requires a known fact.  
4. **Walk-forward backtests only** — at time *t*, use data available ≤ *t*.  
5. **Calibrate by regime:** strategy × state/region × size band × price band.  
6. **Optimize for decision utility**, not RMSE: precision@K, excess return of top decile, false-positive rate on “INVESTIGATE IMMEDIATELY.”  
7. **Human labels:** analysts tag true mispricings / rejected traps; models train against those.  
8. **Champion/challenger weights** — config weights never sacred; promote only after out-of-sample lift.  
9. **Always show rule-based analysis beside any ML output.**  
10. **Asymmetry and Risk are first-class**, never collapsed into one vanity score.

### Minimum viable empiricism (Phase 2+)
- Historical listings with observed outcomes (sale price, DOM, withdrawn)  
- Feature ablation + isotonic calibration of score → outcome probability  
- Survival models for time-to-sale  
- Stability tests under parcel-match noise  

Until then: **rules + explicit assumptions + confidence**, not pretend ML alpha.

---

## Product implications for Phase 1

Ship a vertical slice that is honest:
- Ingest (manual URL/CSV/parcel ID + provider interface)
- Normalize to Parcel Digital Twin
- Run public geospatial screens (soils/flood/wetlands/terrain) with provenance
- Score with versioned explainable engine
- Surface Opportunity Radar + Property Intelligence + Alerts
- Mark every unconfigured commercial integration as `NOT CONFIGURED`
- Never execute purchases
