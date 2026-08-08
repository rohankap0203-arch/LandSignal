# Integrations

Each listing/enrichment source is an adapter implementing a common interface.

## ListingProvider

Required methods:

- `status()` → `CONFIGURED | NOT_CONFIGURED | DEGRADED | ERROR`
- `search_listings(query)`
- `get_listing(external_id)`
- `normalize_listing(raw)`
- `detect_changes(prev, next)`

Implementations live in `apps/api/landsignal/providers/`.

| Adapter | Status without secrets |
|---|---|
| manual / csv | CONFIGURED |
| mls_reso | NOT_CONFIGURED |
| land_com | NOT_CONFIGURED |
| crexi | NOT_CONFIGURED |
| regrid | NOT_CONFIGURED |
| ssurgo / fema / nwi / usgs | CONFIGURED (public) |

Do not scrape sites in violation of terms of service.
