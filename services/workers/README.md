# LandSignal workers

Phase 1 runs enrichment inline in the API for the vertical slice.

This package is the home for Redis/BullMQ-or-RQ workers that will own:

1. `normalize_listing`
2. `resolve_parcel_geometry`
3. `stage1_kill_screens`
4. `soil_analysis` / `flood_analysis` / `wetlands_analysis` / `terrain_analysis`
5. `comps_assemble`
6. `score_v1`
7. `alert_evaluate`

Workers must:

- timeout + retry with exponential backoff
- never crash the pipeline on a single provider failure
- write provenance + knowledge_state
- dead-letter poison jobs

See `apps/api/landsignal/services/analyze.py` for the current synchronous orchestration that workers will absorb.
