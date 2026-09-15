# LandSignal durable data

Runtime dumps survive cloud pod `/tmp` wipes when written here:

- `landsignal_inventory.json` — GIS/BLM listing book (parcels + listings + scores).
  Override path with `LANDSIGNAL_INVENTORY_PATH`. Legacy fallback: `/tmp/landsignal_inventory.json`.
- `attom_enrichment.json` — ATTOM parcel IQ reserve. Created when a live ATTOM key
  presents fields. After key expiry, set `ATTOM_DATA_MODE=memory` so reserved IQ still serves.

These `*.json` files are gitignored; they are rebuilt by `POST /v1/discover` and ATTOM harvest.
