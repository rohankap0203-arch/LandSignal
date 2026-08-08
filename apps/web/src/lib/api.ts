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
};

export type SearchMeta = {
  states: string[];
  state_codes?: string[];
  regions: string[];
  regions_by_state?: Record<string, string[]>;
  strategies: string[];
  hold_years: Array<string | number>;
  target_roi: Array<string | number>;
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
  target_roi?: number | null;
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
  memo: (id: string) =>
    api<{ markdown: string; verdict: string }>(`/parcels/${id}/memo`, { method: "POST" }),
  alerts: () => api<Record<string, unknown>[]>("/alerts"),
  createAlertRule: (body: {
    name: string;
    predicate: Record<string, number>;
    channels: string[];
  }) => api("/alerts/rules", { method: "POST", body: JSON.stringify(body) }),
  profile: () => api<Record<string, unknown>>("/investor-profile"),
  updateProfile: (body: Record<string, unknown>) =>
    api("/investor-profile", { method: "PUT", body: JSON.stringify(body) }),
  ingestManual: (body: Record<string, unknown>) =>
    api("/ingest/manual", { method: "POST", body: JSON.stringify(body) }),
  analyze: (id: string) => api(`/parcels/${id}/analyze`, { method: "POST" }),
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
