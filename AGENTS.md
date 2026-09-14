# AGENTS.md

## Cursor Cloud specific instructions

### One master preview port
- **Port 3000 is the only preview entry** (named `LandSignal` in `.cursor/environment.json`). Open that in the Cursor Ports / right-side preview — do not ask the user to juggle `:8000`.
- Internally the API still runs on `:8000`, but the web app proxies `/v1/*` through `apps/web/src/app/v1/[...path]/route.ts` — one URL covers UI + API.
- `scripts/cloud-agent-start.sh` also mirrors `:51866 → :3000` so the IDE plug panel works when Cursor remaps the preview port.
- When the user wants a clickable HTTPS link, run `bash scripts/send-me-my-link.sh` and reply with the printed `https://…trycloudflare.com` URL (same app as `:3000`).

### Stack notes
- **Show matches** needs both processes running: web (`:3000`) and API (`:8000`). If the API is down, the UI shows a clear 503 message — never a raw Next.js Internal Server Error.
- Local API defaults: `STORE_BACKEND=memory`. Use `DEMO_SEED=true` for fixtures; radar **excludes** demo parcels, so run Inventory refresh / `POST /v1/discover` (or leave `AUTO_DISCOVER_ON_STARTUP=true`) before expecting live Show matches results.
- Land Viewer **Closest** chips are site-wide for every listing: prefer `GET /v1/parcels/{id}/nearby?kind=` (authoritative coords) or `GET /v1/nearby?lat=&lon=&kind=`. Sources: Photon + Nominatim + OSRM, with Overpass backup. Opening Land Viewer prefetches all chips into cache. Do not call Overpass from the browser.
- Standard scripts and stack notes live in the root `README.md` and `package.json`.
