# AGENTS.md

## Cursor Cloud specific instructions

### “Send me my link”
When the user says **send me my link** (or equivalent), the agent must:
1. Ensure LandSignal is healthy (`bash scripts/send-me-my-link.sh`, which boots web `:3000` + API `:8000` if needed).
2. Reply with a clickable markdown link to **`http://127.0.0.1:3000/`** (or `http://localhost:3000/`).
3. Never tell them to open a random forwarded port like `:51866` — that is a stale local fallback. Cursor prefers mapping remote `3000` → local `3000` when this agent tab is active. If their plug menu shows only `3000 → 51866`, tell them to close that forward and re-open **port 3000**, or click the link above after making this agent tab active.

### Stack notes
- **Show matches** needs both processes: web (`npm run dev:web` → `:3000`) and API (`npm run dev:api` → `:8000`). The web app proxies `/v1/*` through `apps/web/src/app/v1/[...path]/route.ts`. If the API is down, the UI shows a clear 503 message — never a raw Next.js Internal Server Error.
- Local API defaults: `STORE_BACKEND=memory`. Use `DEMO_SEED=true` for fixtures; radar **excludes** demo parcels, so run Inventory refresh / `POST /v1/discover` (or leave `AUTO_DISCOVER_ON_STARTUP=true`) before expecting live Show matches results.
- Land Viewer **Closest** chips are site-wide for every listing: prefer `GET /v1/parcels/{id}/nearby?kind=` (authoritative coords) or `GET /v1/nearby?lat=&lon=&kind=`. Sources: Photon + Nominatim + OSRM, with Overpass backup. Opening Land Viewer prefetches all chips into cache. Do not call Overpass from the browser.
- Auto-start: `.cursor/environment.json` + `scripts/cloud-agent-install.sh` / `scripts/cloud-agent-start.sh` (ports 3000 + 8000).
- Standard scripts and stack notes live in the root `README.md` and `package.json`.
