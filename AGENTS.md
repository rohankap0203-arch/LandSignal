# AGENTS.md

## Cursor Cloud specific instructions

### “Send me my link”
When the user says **send me my link** (or equivalent), the agent must:
1. Run `bash scripts/send-me-my-link.sh` (boots web `:3000` + API `:8000` if needed, opens a Cloudflare quick tunnel).
2. Reply with the printed **https://…trycloudflare.com** URL as a clickable markdown link.
3. Do **not** rely on Cursor plug ports like `:51866` or assume `localhost:3000` works on the user’s machine (local port conflicts remap it). The public tunnel URL is the reliable clickable preview.

### Stack notes
- **Show matches** needs both processes: web (`npm run dev:web` → `:3000`) and API (`npm run dev:api` → `:8000`). The web app proxies `/v1/*` through `apps/web/src/app/v1/[...path]/route.ts`. If the API is down, the UI shows a clear 503 message — never a raw Next.js Internal Server Error.
- Local API defaults: `STORE_BACKEND=memory`. Use `DEMO_SEED=true` for fixtures; radar **excludes** demo parcels, so run Inventory refresh / `POST /v1/discover` (or leave `AUTO_DISCOVER_ON_STARTUP=true`) before expecting live Show matches results.
- Land Viewer **Closest** chips are site-wide for every listing: prefer `GET /v1/parcels/{id}/nearby?kind=` (authoritative coords) or `GET /v1/nearby?lat=&lon=&kind=`. Sources: Photon + Nominatim + OSRM, with Overpass backup. Opening Land Viewer prefetches all chips into cache. Do not call Overpass from the browser.
- Auto-start: `.cursor/environment.json` + `scripts/cloud-agent-install.sh` / `scripts/cloud-agent-start.sh` (ports 3000 + 8000).
- Standard scripts and stack notes live in the root `README.md` and `package.json`.
