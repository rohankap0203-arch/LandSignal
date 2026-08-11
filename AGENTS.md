# AGENTS.md

## Cursor Cloud specific instructions

- **Show matches** needs both processes: web (`npm run dev:web` → `:3000`) and API (`npm run dev:api` → `:8000`). The web app proxies `/v1/*` through `apps/web/src/app/v1/[...path]/route.ts`. If the API is down, the UI shows a clear 503 message — never a raw Next.js Internal Server Error.
- Local API defaults: `STORE_BACKEND=memory`. Use `DEMO_SEED=true` for fixtures; radar **excludes** demo parcels, so run Inventory refresh / `POST /v1/discover` (or leave `AUTO_DISCOVER_ON_STARTUP=true`) before expecting live Show matches results.
- Land Viewer **Closest** chips call `GET /v1/nearby` (server-side Overpass/Nominatim/OSRM). Do not call Overpass from the browser — that path hung and returned empty results. The endpoint is hard-deadline capped and caches successful hits.
- Standard scripts and stack notes live in the root `README.md` and `package.json`.
