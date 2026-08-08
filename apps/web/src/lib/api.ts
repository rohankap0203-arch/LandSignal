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

export type ActionLink = { label: string; url: string; kind: string };

export type RatingPart = {
  key: string;
  label: string;
  score: number;
  weight_pct: number;
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
  regions: string[];
  strategies: string[];
  hold_years: Array<string | number>;
  target_roi: Array<string | number>;
  price_presets: Array<{ label: string; min: number | null; max: number | null }>;
  acre_presets: Array<{ label: string; min: number | null; max: number | null }>;
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
  q?: string;
};

function toQuery(filters: SearchFilters): string {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([k, v]) => {
    if (v === undefined || v === null || v === "" || v === "Any") return;
    params.set(k, String(v));
  });
  const s = params.toString();
  return s ? `?${s}` : "";
}

export const landsignalApi = {
  radar: (filters: SearchFilters = {}) => api<RadarRow[]>(`/radar${toQuery(filters)}`),
  searchMeta: () => api<SearchMeta>("/search/meta"),
  providers: () => api<Array<{ id: string; kind: string; name: string; status: string; detail?: string }>>("/providers"),
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
  discover: (limit = 30, minAcres = 1, reset = true) =>
    api<Record<string, unknown>>(
      `/discover?limit=${limit}&min_acres=${minAcres}&max_acres=2500&reset=${reset}`,
      { method: "POST" },
    ),
  health: () => api<Record<string, unknown>>("/health"),
};
