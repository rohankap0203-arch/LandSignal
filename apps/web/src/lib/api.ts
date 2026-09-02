const ENV_API_BASE = process.env.NEXT_PUBLIC_API_URL || "/v1";

/**
 * Prefer same-origin `/v1` (Next rewrite → API) in the browser when the env
 * points at localhost — absolute http://127.0.0.1:8000 breaks phones/tunnels
 * because that host is the user's device, not this server.
 */
function apiBase(): string {
  const base = ENV_API_BASE || "/v1";
  if (typeof window === "undefined") return base;
  if (/^https?:\/\/(localhost|127\.0\.0\.1)(:|\/|$)/i.test(base)) return "/v1";
  return base;
}

function friendlyApiError(status: number, body: string): string {
  const trimmed = (body || "").trim();
  try {
    const parsed = JSON.parse(trimmed) as { detail?: unknown; message?: unknown };
    const detail = parsed.detail ?? parsed.message;
    if (typeof detail === "string" && detail.trim()) return detail.trim();
    if (Array.isArray(detail) && detail.length) {
      const first = detail[0] as { msg?: string } | string;
      if (typeof first === "string") return first;
      if (first && typeof first.msg === "string") return first.msg;
    }
  } catch {
    /* not JSON */
  }
  if (
    !trimmed ||
    /^Internal Server Error$/i.test(trimmed) ||
    trimmed.startsWith("<!DOCTYPE") ||
    trimmed.startsWith("<html")
  ) {
    if (status === 404) {
      return "Analyze service route not found. Refresh the page — if it keeps failing, restart the LandSignal API.";
    }
    if (status === 502 || status === 503 || status === 504) {
      return "LandSignal API is not reachable. Start it with `npm run dev:api`, then try Show matches again.";
    }
    return "Search could not reach the LandSignal API. Start `npm run dev:api`, then try Show matches again.";
  }
  if (status === 404 && /^not found$/i.test(trimmed)) {
    return "Analyze service route not found. Refresh the page — if it keeps failing, restart the LandSignal API.";
  }
  return trimmed.length > 280 ? `API ${status}` : trimmed;
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${apiBase()}${path}`, {
      ...init,
      headers: {
        ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
        ...(init?.headers || {}),
      },
      cache: "no-store",
    });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    if (init?.signal?.aborted) throw new DOMException("Aborted", "AbortError");
    throw new Error(
      "LandSignal API is not reachable. Start it with `npm run dev:api`, then try Show matches again.",
    );
  }
  if (!res.ok) {
    const text = await res.text();
    throw new Error(friendlyApiError(res.status, text));
  }
  return res.json() as Promise<T>;
}

export function num(v: unknown, fallback = 0): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

export type ActionLink = {
  label: string;
  url: string;
  kind: string;
  available?: boolean;
  availability_reason?: string;
  status_code?: number | null;
};

export type UrlAnalyzeStage = {
  id: string;
  label: string;
  status: string;
  detail?: string;
  ms?: number;
};

export type UrlAnalyzeResult = {
  ok: boolean;
  error?: string | null;
  status?: string;
  draft?: Record<string, unknown>;
  missing?: string[];
  missing_material?: Array<{ field: string; label: string; prompt: string; unit?: string }>;
  needs_confirmation?: boolean;
  fetch_status?: string;
  note?: string | null;
  source_host?: string;
  source_domain?: string;
  facts?: string[];
  stages?: UrlAnalyzeStage[];
  identity?: Record<string, unknown>;
  confidence?: { overall?: number; categories?: Record<string, number> };
  conflicts?: Array<Record<string, unknown>>;
  fallback?: {
    message: string;
    options?: Array<{ id: string; label: string; href?: string }>;
  } | null;
  imported_listing?: {
    label?: string;
    domain?: string;
    source_url?: string;
    view_original?: string;
  };
  parcel_id?: string | null;
  listing_id?: string | null;
  score_id?: string | null;
  report_path?: string;
  duplicate?: { parcel_id?: string; message?: string; reason?: string } | null;
};

export type LandAlertMatchCard = {
  id: string;
  profile_id: string;
  parcel_id: string;
  status: "new" | "unseen" | "viewed" | string;
  origin: string;
  is_new_discovery: boolean;
  update_kind?: string | null;
  preference_match_pct: number;
  landsignal_score: number;
  why_matched: string[];
  watch_flags: string[];
  imagery_url?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  has_boundary?: boolean;
  polygon?: number[][][] | null;
  property_name: string;
  location: string;
  state?: string | null;
  county?: string | null;
  asking_price?: number | null;
  asking_price_display?: string | null;
  acres?: number | null;
  acres_display?: string | null;
  price_per_acre?: number | null;
  price_per_acre_display?: string | null;
  land_type: string;
  signal?: string | null;
  best_strategy?: string | null;
  risk?: number | null;
  deep_link: string;
  opportunity_indicators?: string[];
  risk_indicators?: string[];
  contact_website?: string | null;
  contact_phone?: string | null;
  contact_office?: string | null;
  find_parcel_url?: string | null;
  find_parcel_label?: string | null;
  apn?: string | null;
  links?: ActionLink[];
};

export type RatingPart = {
  key: string;
  label: string;
  simple?: string;
  plain_english?: string;
  score: number;
  score_display?: string;
  weight_pct: number;
  weight_display?: string;
  evidence: string[];
  knowledge_state: string;
};

export type RadarRow = {
  parcel_id: string;
  listing_id?: string;
  signal: "EXCEPTIONAL" | "STRONG" | "WATCH" | "REJECT";
  property_name: string;
  location: string;
  state: string | null;
  county: string | null;
  region: string | null;
  acres: number | null;
  acres_display: string;
  ask: number | null;
  price_display: string;
  price_label: string;
  price_per_acre: number | null;
  price_per_acre_display: string;
  estimated_value: number | null;
  estimated_value_display: string;
  value_knowledge: string;
  discount_pct: number | null;
  discount_display: string;
  discount_help?: string | null;
  opportunity: number;
  asymmetry: number;
  risk: number;
  confidence: number;
  deal_readiness: number;
  best_strategy: string | null;
  best_strategy_label: string;
  secondary_strategy_label: string;
  freshness_hours: number | null;
  status: string;
  status_label: string;
  is_demo: boolean;
  personalized_opportunity: number | null;
  fit_score: number | null;
  summary: string;
  match_reasons: string[];
  rating_breakdown: RatingPart[];
  links: ActionLink[];
  latitude: number | null;
  longitude: number | null;
  provider_id: string | null;
  provider_label: string;
  headline_metric: string;
  risk_label: string;
  confidence_label: string;
  source_name?: string | null;
  contact_office?: string | null;
  contact_phone?: string | null;
  contact_website?: string | null;
  how_to_buy?: string | null;
  return_thesis?: string | null;
  conviction?: string | null;
  scout_note?: string | null;
  trajectory_regime?: string | null;
  trajectory_label?: string | null;
  trajectory_cagr_5y?: string | null;
  trajectory_sparkline?: number[];
};

export type SearchMeta = {
  states: string[];
  state_codes?: string[];
  regions: string[];
  regions_by_state?: Record<string, string[]>;
  strategies: string[];
  hold_years: Array<string | number>;
  target_roi?: Array<string | number>;
  max_risk?: Array<string | number>;
  min_confidence?: Array<string | number>;
  price_presets: Array<{ label: string; min: number | null; max: number | null }>;
  acre_presets: Array<{ label: string; min: number | null; max: number | null }>;
  market_channels?: Array<{ value: string; label: string }>;
  unpriced_options?: Array<{ value: string; label: string }>;
  sort_options?: Array<{ value: string; label: string }>;
  tooltips?: Record<string, { title: string; body: string }>;
  inventory_states?: string[];
  inventory_count?: number;
  allows_custom?: string[];
};

export type SearchFilters = {
  state?: string;
  region?: string;
  min_price?: number | null;
  max_price?: number | null;
  min_acres?: number | null;
  max_acres?: number | null;
  strategy?: string;
  min_score?: number | null;
  max_risk?: number | null;
  min_confidence?: number | null;
  hold_years?: number | null;
  include_unpriced?: boolean;
  unpriced_mode?: string;
  market_channel?: string;
  sort?: string;
  q?: string;
  broaden?: boolean;
};

function toQuery(filters: SearchFilters): string {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([k, v]) => {
    if (v === undefined || v === null || v === "" || v === "Any") return;
    if (typeof v === "number" && !Number.isFinite(v)) return;
    if (typeof v === "string" && (v === "__custom__" || v === "CUSTOM" || v === "NaN")) return;
    params.set(k, String(v));
  });
  const s = params.toString();
  return s ? `?${s}` : "";
}

export const landsignalApi = {
  radar: (filters: SearchFilters = {}) => api<RadarRow[]>(`/radar${toQuery(filters)}`),
  searchMeta: () => api<SearchMeta>("/search/meta"),
  providers: () =>
    api<Array<{ id: string; kind: string; name: string; status: string; detail?: string }>>("/providers"),
  parcel: (id: string) => api<Record<string, unknown>>(`/parcels/${id}`),
  catalystSimulate: (
    id: string,
    body: { scenario_ids?: string[]; custom_text?: string; stress_case?: string },
  ) =>
    api<Record<string, unknown>>(`/parcels/${id}/catalyst-simulate`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  parcelGeometry: (id: string) =>
    api<{
      parcel_id: string;
      latitude: number | null;
      longitude: number | null;
      polygon: number[][][] | null;
      acres: number | null;
      state?: string | null;
      county?: string | null;
    }>(`/parcels/${id}/geometry`),
  nearby: (lat: number, lon: number, kind: string, init?: RequestInit) =>
    api<{
      kind: string;
      label: string;
      hits: Array<{
        kind: string;
        label: string;
        name: string;
        lat: number;
        lon: number;
        meters: number;
        detail?: string | null;
        osm_key?: string | null;
      }>;
      status: string;
      message?: string | null;
      max_miles?: number | null;
      searched_radius_m?: number | null;
      cached?: boolean;
      parcel_id?: string;
    }>(
      `/nearby?lat=${encodeURIComponent(String(lat))}&lon=${encodeURIComponent(String(lon))}&kind=${encodeURIComponent(kind)}`,
      init,
    ),
  nearbyForParcel: (parcelId: string, kind: string, init?: RequestInit) =>
    api<{
      kind: string;
      label: string;
      hits: Array<{
        kind: string;
        label: string;
        name: string;
        lat: number;
        lon: number;
        meters: number;
        detail?: string | null;
        osm_key?: string | null;
      }>;
      status: string;
      message?: string | null;
      max_miles?: number | null;
      searched_radius_m?: number | null;
      cached?: boolean;
      parcel_id?: string;
    }>(`/parcels/${encodeURIComponent(parcelId)}/nearby?kind=${encodeURIComponent(kind)}`, init),
  memo: (id: string) =>
    api<{ markdown: string; verdict: string }>(`/parcels/${id}/memo`, { method: "POST" }),
  alerts: () => api<Record<string, unknown>[]>("/alerts"),
  createAlertRule: (body: {
    name: string;
    predicate: Record<string, number>;
    channels: string[];
  }) => api("/alerts/rules", { method: "POST", body: JSON.stringify(body) }),
  landAlertProfile: () =>
    api<{
      profile: Record<string, unknown> | null;
      has_profile: boolean;
      notify: Record<string, unknown>;
      preferences: Record<string, unknown>;
    }>("/land-alerts/profile"),
  upsertLandAlertProfile: (body: Record<string, unknown>) =>
    api<{
      profile: Record<string, unknown>;
      match_count: number;
      new_count: number;
      matches: LandAlertMatchCard[];
      note?: string;
    }>("/land-alerts/profile", { method: "PUT", body: JSON.stringify(body) }),
  landAlertMatches: (profileId?: string, status?: string) => {
    const qs = new URLSearchParams();
    if (profileId) qs.set("profile_id", profileId);
    if (status) qs.set("status", status);
    const q = qs.toString();
    return api<{
      matches: LandAlertMatchCard[];
      counts: { new: number; unseen: number; viewed: number; total: number };
    }>(`/land-alerts/matches${q ? `?${q}` : ""}`);
  },
  pauseLandAlert: (profileId: string) =>
    api(`/land-alerts/profile/${profileId}/pause`, { method: "POST" }),
  resumeLandAlert: (profileId: string) =>
    api(`/land-alerts/profile/${profileId}/resume`, { method: "POST" }),
  markLandAlertViewed: (parcelId: string) =>
    api(`/land-alerts/matches/${parcelId}/viewed`, { method: "POST" }),
  unmarkLandAlertViewed: (parcelId: string) =>
    api(`/land-alerts/matches/${parcelId}/viewed`, { method: "DELETE" }),
  markAllLandAlertsSeen: (profileId?: string) => {
    const q = profileId ? `?profile_id=${profileId}` : "";
    return api<{ updated: number }>(`/land-alerts/mark-all-seen${q}`, { method: "POST" });
  },
  markAllLandAlertsUnseen: (profileId?: string) => {
    const q = profileId ? `?profile_id=${profileId}` : "";
    return api<{ updated: number }>(`/land-alerts/mark-all-unseen${q}`, { method: "POST" });
  },
  updateLandAlertNotify: (body: Record<string, unknown>) =>
    api("/land-alerts/notify", { method: "PUT", body: JSON.stringify(body) }),
  rescanLandAlerts: () =>
    api<{ match_count: number; matches: LandAlertMatchCard[] }>("/land-alerts/rescan", {
      method: "POST",
    }),
  profile: () => api<Record<string, unknown>>("/investor-profile"),
  updateProfile: (body: Record<string, unknown>) =>
    api("/investor-profile", { method: "PUT", body: JSON.stringify(body) }),
  ingestManual: (body: Record<string, unknown>) =>
    api("/ingest/manual", { method: "POST", body: JSON.stringify(body) }),
  ingestFromUrl: (url: string) =>
    api<{
      ok: boolean;
      error?: string | null;
      draft?: Record<string, unknown>;
      missing?: string[];
      fetch_status?: string;
      note?: string | null;
      source_host?: string;
    }>("/ingest/from-url", { method: "POST", body: JSON.stringify({ url }) }),
  analyzeListingUrl: (url: string, opts?: { corrections?: Record<string, unknown>; force_refresh?: boolean }) =>
    api<UrlAnalyzeResult>("/ingest/from-url/analyze", {
      method: "POST",
      body: JSON.stringify({
        url,
        corrections: opts?.corrections || null,
        force_refresh: Boolean(opts?.force_refresh),
      }),
    }),
  analyze: (id: string) => api(`/parcels/${id}/analyze`, { method: "POST" }),
  watch: (id: string) => api<Record<string, unknown>>(`/parcels/${id}/watch`, { method: "POST" }),
  unwatch: (id: string) => api<Record<string, unknown>>(`/parcels/${id}/watch`, { method: "DELETE" }),
  watchlist: () =>
    api<{
      items: Array<Record<string, unknown>>;
      notify_email: string;
      watchlist_email_updates: boolean;
    }>("/watchlist"),
  discover: (
    limit = 10000,
    minAcres = 0.1,
    reset = false,
    states?: string,
    background = true,
  ) => {
    const qs = new URLSearchParams({
      limit: String(limit),
      min_acres: String(minAcres),
      max_acres: "50000",
      reset: String(reset),
      background: String(background),
      fast: "true",
    });
    if (states) qs.set("states", states);
    return api<Record<string, unknown>>(`/discover?${qs}`, { method: "POST" });
  },
  health: () => api<Record<string, unknown>>("/health"),
};
