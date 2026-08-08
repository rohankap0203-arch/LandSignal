# Risks & Assumptions

## Assumptions we accept for Phase 1
- Human investor makes every acquisition decision  
- Public FEMA/NWI/SSURGO/3DEP are screening-grade, not survey-grade  
- Demo fixtures may exist for UI/dev and are labeled `DEMO`  
- Single-tenant local auth is sufficient for Phase 1  
- Mapbox token may be absent  

## Key risks
| Risk | Mitigation |
|---|---|
| Parcel mismatch | Explicit geometry confidence; MANUAL_REVIEW |
| False precision in scores | Confidence + provenance; intervals later |
| ToS / legal scraping | Adapter-only licensed/manual sources |
| API outages | Circuit breakers; partial enrichment |
| Overfitting weights | Versioning + future walk-forward tests |
| User treats score as appraisal | UI disclaimers; Deal Readiness separate |
| Secrets in repo | `.env.example` only; runtime env |

## Compliance posture
- No automated purchasing  
- No protected-class seller inference  
- Screening ≠ legal diligence  
