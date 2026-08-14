const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/v1";

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `API ${res.status}`);
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
  asking_price_display: string;
  acres?: number | null;
  acres_display: string;
  price_per_acre?: number | null;
  price_per_acre_display: string;
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
  match_tier?: "exact" | "near";
  near_match_reason?: string | null;
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
  data_mode?: string;
  inventory_label?: string;
  active_land_listings?: number;
  cadastral_screens?: number;
  states_covered?: number;
  states_total?: number;
  counties_covered?: number;
  listings_added_24h?: number;
  listings_updated_24h?: number;
  inventory_warnings?: string[];
  by_state_counts?: Record<string, number>;
  allows_custom?: string[];
};

export type SearchEstimate = {
  exact_match_count: number;
  filters: Record<string, unknown>;
  facets: {
    regions: Array<{ label: string; count: number }>;
    price_ranges: Array<{ label: string; count: number }>;
    acre_ranges: Array<{ label: string; count: number }>;
    counties: Array<{ label: string; count: number }>;
  };
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
  searchEstimate: (filters: SearchFilters = {}) =>
    api<SearchEstimate>(`/search/estimate${toQuery(filters)}`),
  inventoryHealth: () => api<Record<string, unknown>>("/inventory/health"),
  providers: () =>
    api<Array<{ id: string; kind: string; name: string; status: string; detail?: string }>>("/providers"),
  parcel: (id: string) => api<Record<string, unknown>>(`/parcels/${id}`),
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
