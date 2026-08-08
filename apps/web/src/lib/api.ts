// Same-origin `/v1` so phone/tunnel clients don't need a separate API host.
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

export type RadarRow = {
  parcel_id: string;
  listing_id?: string;
  signal: "EXCEPTIONAL" | "STRONG" | "WATCH" | "REJECT";
  property_name: string;
  location: string;
  acres: number | null;
  ask: number | null;
  price_per_acre: number | null;
  estimated_value: number | null;
  discount_pct: number | null;
  opportunity: number;
  asymmetry: number;
  risk: number;
  confidence: number;
  best_strategy: string | null;
  freshness_hours: number | null;
  status: string;
  is_demo: boolean;
  personalized_opportunity: number | null;
};

export type ProviderInfo = {
  id: string;
  kind: string;
  name: string;
  status: string;
  detail?: string | null;
};

export const landsignalApi = {
  radar: () => api<RadarRow[]>("/radar"),
  providers: () => api<ProviderInfo[]>("/providers"),
  parcel: (id: string) => api<Record<string, unknown>>(`/parcels/${id}`),
  memo: (id: string) =>
    api<{ markdown: string; verdict: string }>(`/parcels/${id}/memo`, { method: "POST" }),
  alerts: () => api<Record<string, unknown>[]>("/alerts"),
  createAlertRule: (body: {
    name: string;
    predicate: Record<string, number>;
    channels: string[];
  }) =>
    api("/alerts/rules", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  profile: () => api<Record<string, unknown>>("/investor-profile"),
  updateProfile: (body: Record<string, unknown>) =>
    api("/investor-profile", { method: "PUT", body: JSON.stringify(body) }),
  ingestManual: (body: Record<string, unknown>) =>
    api("/ingest/manual", { method: "POST", body: JSON.stringify(body) }),
  analyze: (id: string) => api(`/parcels/${id}/analyze`, { method: "POST" }),
  health: () => api<Record<string, unknown>>("/health"),
};

export function money(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(n);
}

export function pct(n: number | null | undefined, digits = 1): string {
  if (n == null || Number.isNaN(n)) return "—";
  return `${n.toFixed(digits)}%`;
}

export function num(n: number | null | undefined, digits = 1): string {
  if (n == null || Number.isNaN(n)) return "—";
  return n.toFixed(digits);
}
