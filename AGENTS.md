# AGENTS.md

## Cursor Cloud specific instructions

- **Show matches** needs both processes: web (`npm run dev:web` → `:3000`) and API (`npm run dev:api` → `:8000`). The web app proxies `/v1/*` through `apps/web/src/app/v1/[...path]/route.ts`. If the API is down, the UI shows a clear 503 message — never a raw Next.js Internal Server Error.
- Local API defaults: `STORE_BACKEND=memory`. Use `DEMO_SEED=true` for fixtures; radar **excludes** demo parcels, so run Inventory refresh / `POST /v1/discover` (or leave `AUTO_DISCOVER_ON_STARTUP=true`) before expecting live Show matches results.
- Standard scripts and stack notes live in the root `README.md` and `package.json`.
