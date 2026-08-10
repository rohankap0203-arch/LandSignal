"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AcquireRail } from "@/components/acquire-rail";
import { HelpTip } from "@/components/filter-field";
import { LandAlertsLoader } from "@/components/land-alerts-loader";
import { LandViewerModal, ViewLandButton } from "@/components/land-viewer-modal";
import { LiveMagnifier } from "@/components/live-magnifier";
import { landsignalApi, type LandAlertMatchCard } from "@/lib/api";

type PrefMode = "must" | "prefer" | "flexible";

type Interests = {
  agricultural: boolean;
  recreational: boolean;
  residential_dev: boolean;
  commercial_dev: boolean;
  timber: boolean;
  land_banking: boolean;
  development: boolean;
};

type FormState = {
  name: string;
  states: string;
  states_mode: PrefMode;
  budget_min: string;
  budget_max: string;
  budget_mode: PrefMode;
  acres_min: string;
  acres_max: string;
  acres_mode: PrefMode;
  strategies: string[];
  land_types: string[];
  hold_years_min: string;
  hold_years_max: string;
  desired_return_pct: string;
  max_risk: string;
  interests: Interests;
  infrastructure_prefs: string[];
  email: boolean;
  sms: boolean;
  in_app: boolean;
  push: boolean;
  sensitivity: string;
  frequency: string;
  email_address: string;
  phone: string;
};

const DEFAULT_FORM: FormState = {
  name: "My Land Alert",
  states: "",
  states_mode: "must",
  budget_min: "",
  budget_max: "",
  budget_mode: "prefer",
  acres_min: "",
  acres_max: "",
  acres_mode: "prefer",
  strategies: ["LAND_BANK"],
  land_types: [],
  hold_years_min: "",
  hold_years_max: "",
  desired_return_pct: "",
  max_risk: "moderate",
  interests: {
    agricultural: false,
    recreational: false,
    residential_dev: false,
    commercial_dev: false,
    timber: false,
    land_banking: true,
    development: false,
  },
  infrastructure_prefs: ["road_access"],
  email: true,
  sms: false,
  in_app: true,
  push: false,
  sensitivity: "strong",
  frequency: "immediate",
  email_address: "",
  phone: "",
};

const STRATEGY_OPTS = [
  { id: "LAND_BANK", label: "Land banking" },
  { id: "FARMLAND", label: "Farmland" },
  { id: "DEVELOPMENT", label: "Development" },
  { id: "RECREATIONAL", label: "Recreational" },
  { id: "TIMBER", label: "Timber" },
  { id: "ENERGY", label: "Energy" },
];

const LAND_TYPE_OPTS = ["Vacant", "Raw land", "Farmland", "Timber", "Recreational", "Residential lot", "Commercial"];

const INTEREST_OPTS = [
  ["land_banking", "Land banking"] as const,
  ["agricultural", "Farmland"] as const,
  ["recreational", "Recreational"] as const,
  ["residential_dev", "Residential devel."] as const,
  ["commercial_dev", "Commercial devel."] as const,
  ["timber", "Timber"] as const,
  ["development", "General devel."] as const,
];

const INFRA_OPTS = [
  ["road_access", "Road access"],
  ["utilities", "Utilities"],
  ["power", "Power nearby"],
  ["water", "Water access"],
] as const;

const STATE_REGIONS: { id: string; label: string; states: string[] }[] = [
  { id: "southeast", label: "Southeast", states: ["AL", "AR", "FL", "GA", "KY", "LA", "MS", "NC", "SC", "TN", "VA", "WV"] },
  { id: "southwest", label: "Southwest", states: ["AZ", "NM", "OK", "TX"] },
  { id: "midwest", label: "Midwest", states: ["IA", "IL", "IN", "KS", "MI", "MN", "MO", "ND", "NE", "OH", "SD", "WI"] },
  { id: "west", label: "West", states: ["AK", "CA", "CO", "HI", "ID", "MT", "NV", "OR", "UT", "WA", "WY"] },
  { id: "northeast", label: "Northeast", states: ["CT", "DE", "MA", "MD", "ME", "NH", "NJ", "NY", "PA", "RI", "VT"] },
];

const ALL_STATES = STATE_REGIONS.flatMap((r) => r.states);

const BUDGET_PRESETS: { id: string; label: string; min: string; max: string }[] = [
  { id: "any", label: "Any", min: "", max: "" },
  { id: "25k", label: "Up to $25k", min: "", max: "25000" },
  { id: "50k", label: "Up to $50k", min: "", max: "50000" },
  { id: "100k", label: "Up to $100k", min: "", max: "100000" },
  { id: "150k", label: "Up to $150k", min: "", max: "150000" },
  { id: "250k", label: "Up to $250k", min: "", max: "250000" },
  { id: "500k", label: "Up to $500k", min: "", max: "500000" },
  { id: "1m", label: "Up to $1M", min: "", max: "1000000" },
  { id: "2_5m", label: "Up to $2.5M", min: "", max: "2500000" },
  { id: "5m", label: "Up to $5M", min: "", max: "5000000" },
  { id: "custom", label: "Custom", min: "", max: "" },
];

const ACRE_PRESETS: { id: string; label: string; min: string; max: string }[] = [
  { id: "any", label: "Any", min: "", max: "" },
  { id: "1", label: "1+ ac", min: "1", max: "" },
  { id: "5", label: "5+ ac", min: "5", max: "" },
  { id: "10", label: "10+ ac", min: "10", max: "" },
  { id: "20", label: "20+ ac", min: "20", max: "" },
  { id: "40", label: "40+ ac", min: "40", max: "" },
  { id: "80", label: "80+ ac", min: "80", max: "" },
  { id: "160", label: "160+ ac", min: "160", max: "" },
  { id: "320", label: "320+ ac", min: "320", max: "" },
  { id: "custom", label: "Custom", min: "", max: "" },
];

const HOLD_PRESETS: { id: string; label: string; min: string; max: string }[] = [
  { id: "any", label: "Any hold", min: "", max: "" },
  { id: "flip", label: "1–5 yrs", min: "1", max: "5" },
  { id: "mid", label: "5–15 yrs", min: "5", max: "15" },
  { id: "long", label: "10–25 yrs", min: "10", max: "25" },
  { id: "mid_long", label: "25–50 yrs", min: "25", max: "50" },
  { id: "long_hold", label: "50–75 yrs", min: "50", max: "75" },
  { id: "legacy", label: "75–100+ yrs", min: "75", max: "" },
  { id: "custom", label: "Custom", min: "", max: "" },
];

const RETURN_PRESETS: { id: string; label: string; value: string }[] = [
  { id: "any", label: "Any return", value: "" },
  { id: "4", label: "4%+", value: "4" },
  { id: "8", label: "8%+", value: "8" },
  { id: "12", label: "12%+", value: "12" },
  { id: "15", label: "15%+", value: "15" },
  { id: "20", label: "20%+", value: "20" },
];

const ALL_STRATEGY_IDS = STRATEGY_OPTS.map((s) => s.id);
const ALL_INTEREST_KEYS = INTEREST_OPTS.map(([key]) => key);
const ALL_INFRA_IDS = INFRA_OPTS.map(([id]) => id);

const RISK_OPTS = [
  { id: "low", label: "Low" },
  { id: "moderate", label: "Moderate" },
  { id: "high", label: "High" },
  { id: "very_high", label: "Very high" },
];

const SENSITIVITY_OPTS = [
  { id: "exceptional", label: "Exceptional only" },
  { id: "strong", label: "Strong matches" },
  { id: "all", label: "All matches" },
];

const FREQUENCY_OPTS = [
  { id: "immediate", label: "Immediate" },
  { id: "daily_digest", label: "Daily digest" },
  { id: "weekly_digest", label: "Weekly digest" },
  { id: "in_app_only", label: "In-app only" },
];

const PROFILE_NAME_PRESETS = ["My Land Alert", "Farmland hunt", "Land bank watch", "Development sites"];

function parseNum(v: string): number | undefined {
  const n = Number(String(v).replace(/[$,\s]/g, ""));
  return Number.isFinite(n) ? n : undefined;
}

function parseStates(raw: string): string[] {
  return raw
    .split(/[,;\s]+/)
    .map((s) => s.trim().toUpperCase())
    .filter((s) => /^[A-Z]{2}$/.test(s));
}

function matchPreset(
  presets: { id: string; min: string; max: string }[],
  min: string,
  max: string,
): string {
  const hit = presets.find((p) => p.id !== "custom" && p.min === min && p.max === max);
  if (hit) return hit.id;
  if (!min && !max) return "any";
  return "custom";
}

function ModeToggle({
  value,
  onChange,
}: {
  value: PrefMode;
  onChange: (m: PrefMode) => void;
}) {
  return (
    <div className="acq-mode" role="group" aria-label="Preference strength">
      {(
        [
          ["must", "Must"],
          ["prefer", "Prefer"],
          ["flexible", "Flexible"],
        ] as const
      ).map(([id, label]) => (
        <button
          key={id}
          type="button"
          className={`acq-mode-btn${value === id ? " on" : ""}`}
          aria-pressed={value === id}
          onClick={() => onChange(id)}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

function SwitchToggle({
  checked,
  onChange,
  label,
  hint,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  label: string;
  hint?: string;
}) {
  return (
    <button
      type="button"
      className={`acq-switch${checked ? " on" : ""}`}
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
    >
      <span className="acq-switch-track" aria-hidden>
        <span className="acq-switch-thumb" />
      </span>
      <span className="acq-switch-copy">
        <span className="acq-switch-label">{label}</span>
        {hint ? <span className="acq-switch-hint">{hint}</span> : null}
      </span>
    </button>
  );
}

/** One card per parcel / property / near-identical batch — newest first. */
function dedupeRecentLandAlerts(alerts: Record<string, unknown>[]): Record<string, unknown>[] {
  const seenParcel = new Set<string>();
  const seenProp = new Set<string>();
  const seenSoft = new Set<string>();
  const out: Record<string, unknown>[] = [];
  for (const alert of alerts) {
    if (String(alert.severity || "") !== "LAND_ALERT") continue;
    const body = (alert.body || {}) as Record<string, unknown>;
    if (body.has_boundary === false) continue;
    const parcelKey = String(alert.parcel_id || "");
    const propKey = `${String(body.property || "")
      .trim()
      .toLowerCase()}|${String(body.location || "")
      .trim()
      .toLowerCase()}`;
    const acresNum = Number(body.acres);
    const matchNum = Number(body.preference_match_pct);
    const softKey = [
      String(body.location || "")
        .trim()
        .toLowerCase(),
      Number.isFinite(acresNum) ? String(Math.round(acresNum)) : "",
      String(body.update_kind || "new_listing")
        .trim()
        .toLowerCase(),
      Number.isFinite(matchNum) ? String(Math.round(matchNum / 5) * 5) : "",
    ].join("|");
    if (!parcelKey || seenParcel.has(parcelKey)) continue;
    if (propKey !== "|" && seenProp.has(propKey)) continue;
    if (softKey !== "|||" && seenSoft.has(softKey)) continue;
    seenParcel.add(parcelKey);
    if (propKey !== "|") seenProp.add(propKey);
    if (softKey !== "|||") seenSoft.add(softKey);
    out.push(alert);
  }
  return out;
}

function parseScoutedDate(raw: unknown): Date | null {
  if (raw == null || raw === "") return null;
  let text = String(raw).trim();
  if (!text) return null;
  // Naive ISO from the API is UTC — force Z so browsers don't treat it as local.
  if (/^\d{4}-\d{2}-\d{2}T/.test(text) && !/(Z|[+-]\d{2}:?\d{2})$/.test(text)) {
    text = `${text}Z`;
  }
  const d = new Date(text);
  if (Number.isNaN(d.getTime())) return null;
  const now = Date.now();
  // Never show a future "retrieved" time.
  if (d.getTime() > now + 15_000) return new Date(now);
  return d;
}

function formatScoutedAt(alert: Record<string, unknown>): string | null {
  const body = (alert.body || {}) as Record<string, unknown>;
  const d = parseScoutedDate(body.scouted_at || body.retrieved_at || alert.created_at);
  if (!d) return null;
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function MatchCard({
  row,
  dimmed,
  onToggleSeen,
}: {
  row: LandAlertMatchCard;
  dimmed: boolean;
  onToggleSeen: (parcelId: string, nextChecked: boolean) => void;
}) {
  const [flipped, setFlipped] = useState(false);
  const [animating, setAnimating] = useState(false);
  const [snapPose, setSnapPose] = useState(false);
  const [viewerOpen, setViewerOpen] = useState(false);
  const [viewerPolygon, setViewerPolygon] = useState<number[][][] | null>(row.polygon ?? null);
  const flipTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const href = row.deep_link || `/parcels/${row.parcel_id}`;
  const canViewLand =
    row.has_boundary === true && row.latitude != null && row.longitude != null;

  useEffect(() => {
    return () => {
      if (flipTimer.current) clearTimeout(flipTimer.current);
    };
  }, []);

  useEffect(() => {
    if (!viewerOpen) return;
    if (viewerPolygon?.[0]?.length) return;
    let cancelled = false;
    void landsignalApi
      .parcelGeometry(row.parcel_id)
      .then((g) => {
        if (!cancelled && g.polygon) setViewerPolygon(g.polygon);
      })
      .catch(() => null);
    return () => {
      cancelled = true;
    };
  }, [viewerOpen, row.parcel_id, viewerPolygon]);

  function flipToggle() {
    if (animating || viewerOpen) return;
    setSnapPose(true);
    setAnimating(true);
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        setSnapPose(false);
        requestAnimationFrame(() => {
          setFlipped((v) => !v);
        });
      });
    });
    if (flipTimer.current) clearTimeout(flipTimer.current);
    flipTimer.current = setTimeout(() => {
      setAnimating(false);
      setSnapPose(false);
    }, 680);
  }

  return (
    <div
      className={`land-alert-flip${flipped ? " is-flipped" : ""}${animating ? " is-animating" : ""}${snapPose ? " is-snap-pose" : ""}${row.status === "new" && !dimmed ? " is-new" : ""}${dimmed ? " is-dimmed" : ""}`}
    >
      <div className="land-alert-flip-inner">
        <article
          className="land-alert-card land-alert-card-front"
          onClick={flipToggle}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              flipToggle();
            }
          }}
          role="button"
          tabIndex={0}
          aria-expanded={flipped}
          aria-label={`Flip card for ${row.property_name}`}
        >
          <div className="land-alert-card-top">
            <div className="land-alert-card-scores">
              <span className="land-alert-match-pct">
                {Math.round(row.preference_match_pct)}% Match
              </span>
              <span className="land-alert-ls-score">
                {Math.round(row.landsignal_score)}/100 Score
              </span>
            </div>
            <div className="land-alert-card-badges">
              <label
                className={`land-alert-checkseen${dimmed ? " on" : ""}`}
                title="Save match — moves to Saved"
                onClick={(e) => e.stopPropagation()}
                onKeyDown={(e) => e.stopPropagation()}
              >
                <input
                  type="checkbox"
                  checked={dimmed}
                  onChange={(e) => onToggleSeen(row.parcel_id, e.target.checked)}
                  aria-label="Save match"
                />
                <span className="land-alert-checkseen-box" aria-hidden>
                  {dimmed ? "✓" : ""}
                </span>
              </label>
              {row.status === "new" && !dimmed ? <span className="land-alert-new">NEW</span> : null}
              {row.update_kind && row.update_kind !== "new_listing" ? (
                <span className="land-alert-update">{row.update_kind.replace(/_/g, " ")}</span>
              ) : null}
            </div>
          </div>
          <div className="land-alert-card-title">{row.property_name}</div>
          <div className="land-alert-card-meta">
            <span>{row.location || row.state || "—"}</span>
            {row.asking_price_display ? <span>{row.asking_price_display}</span> : null}
            {row.acres_display ? <span>{row.acres_display}</span> : null}
            {row.price_per_acre_display ? <span>{row.price_per_acre_display}</span> : null}
          </div>
          {row.why_matched?.length ? (
            <ul className="land-alert-why">
              {row.why_matched.slice(0, 3).map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          ) : null}
          {row.watch_flags?.length ? (
            <div className="land-alert-watch">
              <strong>Watch:</strong> {row.watch_flags[0]}
            </div>
          ) : null}
          <div
            className="land-alert-view-land-wrap"
            onClick={(e) => e.stopPropagation()}
            onPointerDown={(e) => e.stopPropagation()}
          >
            <ViewLandButton
              disabled={!canViewLand}
              onClick={() => setViewerOpen(true)}
            />
          </div>
          <div
            className="land-alert-front-actions"
            onClick={(e) => e.stopPropagation()}
            onPointerDown={(e) => e.stopPropagation()}
          >
            <Link href={href} className="btn-intel">
              Open full LandSignal report
            </Link>
          </div>
          <div className="land-alert-flip-hint">Tap to flip</div>
        </article>

        <article
          className="land-alert-card land-alert-card-back"
          onClick={flipToggle}
          role="button"
          tabIndex={0}
          aria-label={`Flip back ${row.property_name}`}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              flipToggle();
            }
          }}
        >
          <div className="land-alert-back-head">
            <p className="land-alert-back-kicker">Contact & next steps</p>
            <div className="land-alert-card-title">{row.property_name}</div>
            <div className="land-alert-card-meta">
              <span>{row.location || row.state || "—"}</span>
              {row.asking_price_display ? <span>{row.asking_price_display}</span> : null}
              {row.acres_display ? <span>{row.acres_display}</span> : null}
            </div>
          </div>

          <div className="land-alert-back-rail" onClick={(e) => e.stopPropagation()}>
            <AcquireRail
              className="land-alert-acquire"
              postingUrl={row.contact_website}
              phone={row.contact_phone}
              office={row.contact_office}
              findUrl={row.find_parcel_url}
              findLabel={row.find_parcel_label || (row.apn ? `ID ${row.apn}` : undefined)}
            />
          </div>

          <div className="land-alert-flip-hint">Tap to flip back</div>
        </article>
      </div>

      <LandViewerModal
        open={viewerOpen}
        onClose={() => setViewerOpen(false)}
        title={row.property_name}
        location={row.location || row.state}
        acresDisplay={row.acres_display}
        priceDisplay={row.asking_price_display}
        latitude={row.latitude}
        longitude={row.longitude}
        polygon={viewerPolygon}
        reportHref={href}
      />
    </div>
  );
}

export default function LandAlertsPage() {
  const [form, setForm] = useState<FormState>(DEFAULT_FORM);
  const [profileId, setProfileId] = useState<string | null>(null);
  const [paused, setPaused] = useState(false);
  const [hasProfile, setHasProfile] = useState(false);
  const [editing, setEditing] = useState(true);
  const [matches, setMatches] = useState<LandAlertMatchCard[]>([]);
  const [counts, setCounts] = useState({ new: 0, unseen: 0, viewed: 0, total: 0 });
  const [tab, setTab] = useState<"matches" | "saved">("matches");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");
  const [inAppAlerts, setInAppAlerts] = useState<Record<string, unknown>[]>([]);
  /** Checked this session — grey in Matches; also listed under Saved */
  const [pendingSaved, setPendingSaved] = useState<Set<string>>(() => new Set());
  const [markAllActive, setMarkAllActive] = useState(false);
  const [bootReady, setBootReady] = useState(false);
  /** Explicit custom panels — avoid forcing placeholder values that jump the layout/summary. */
  const [budgetCustomOpen, setBudgetCustomOpen] = useState(false);
  const [acresCustomOpen, setAcresCustomOpen] = useState(false);
  const [holdCustomOpen, setHoldCustomOpen] = useState(false);

  const loadMatches = useCallback(async () => {
    const data = await landsignalApi.landAlertMatches(profileId || undefined);
    setMatches(data.matches || []);
    setCounts(data.counts || { new: 0, unseen: 0, viewed: 0, total: 0 });
    setPendingSaved(new Set());
    setMarkAllActive(false);
  }, [profileId]);

  const hydrate = useCallback(async () => {
    setLoading(true);
    try {
      const data = await landsignalApi.landAlertProfile();
      if (data.has_profile && data.profile) {
        const p = data.profile;
        const prefs = (data.preferences || {}) as Record<string, unknown>;
        const notify = (data.notify || {}) as Record<string, unknown>;
        const interests = (prefs.interests || {}) as Partial<Interests>;
        setProfileId(String(p.id));
        setPaused(Boolean(p.paused));
        setHasProfile(true);
        setEditing(false);
        const nextBudgetMin = prefs.budget_min != null ? String(prefs.budget_min) : "";
        const nextBudgetMax = prefs.budget_max != null ? String(prefs.budget_max) : "";
        const nextAcresMin = prefs.acres_min != null ? String(prefs.acres_min) : "";
        const nextAcresMax = prefs.acres_max != null ? String(prefs.acres_max) : "";
        const nextHoldMin = prefs.hold_years_min != null ? String(prefs.hold_years_min) : "";
        const nextHoldMax = prefs.hold_years_max != null ? String(prefs.hold_years_max) : "";
        setBudgetCustomOpen(matchPreset(BUDGET_PRESETS, nextBudgetMin, nextBudgetMax) === "custom");
        setAcresCustomOpen(matchPreset(ACRE_PRESETS, nextAcresMin, nextAcresMax) === "custom");
        setHoldCustomOpen(matchPreset(HOLD_PRESETS, nextHoldMin, nextHoldMax) === "custom");
        setForm({
          ...DEFAULT_FORM,
          name: String(p.name || "My Land Alert"),
          states: Array.isArray(prefs.states) ? (prefs.states as string[]).join(", ") : "",
          states_mode: (prefs.states_mode as PrefMode) || "must",
          budget_min: nextBudgetMin,
          budget_max: nextBudgetMax,
          budget_mode: (prefs.budget_mode as PrefMode) || "prefer",
          acres_min: nextAcresMin,
          acres_max: nextAcresMax,
          acres_mode: (prefs.acres_mode as PrefMode) || "prefer",
          strategies: Array.isArray(prefs.strategies) ? (prefs.strategies as string[]) : ["LAND_BANK"],
          land_types: Array.isArray(prefs.land_types)
            ? (prefs.land_types as string[]).map((t) => {
                const hit = LAND_TYPE_OPTS.find((opt) => opt.toLowerCase() === String(t).toLowerCase());
                return hit || t;
              })
            : [],
          hold_years_min: nextHoldMin,
          hold_years_max: nextHoldMax,
          desired_return_pct: prefs.desired_return_pct != null ? String(prefs.desired_return_pct) : "",
          max_risk: String(prefs.max_risk || "moderate"),
          interests: { ...DEFAULT_FORM.interests, ...interests },
          infrastructure_prefs: Array.isArray(prefs.infrastructure_prefs)
            ? (prefs.infrastructure_prefs as string[])
            : ["road_access"],
          email: notify.email !== false,
          sms: Boolean(notify.sms),
          in_app: notify.in_app !== false,
          push: Boolean(notify.push),
          sensitivity: String(notify.sensitivity || "strong"),
          frequency: String(notify.frequency || "immediate"),
          email_address: String(notify.email_address || ""),
          phone: String(notify.phone || ""),
        });
      } else {
        setHasProfile(false);
        setEditing(true);
        setBudgetCustomOpen(false);
        setAcresCustomOpen(false);
        setHoldCustomOpen(false);
      }
      const profileKey =
        data.has_profile && data.profile ? String((data.profile as { id: string }).id) : undefined;
      const [m, alerts] = await Promise.all([
        landsignalApi.landAlertMatches(profileKey),
        landsignalApi.alerts().catch(() => []),
      ]);
      setMatches(m.matches || []);
      setCounts(m.counts || { new: 0, unseen: 0, viewed: 0, total: 0 });
      setInAppAlerts(dedupeRecentLandAlerts(alerts || []).slice(0, 12));
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Could not load Land Alerts");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void hydrate();
  }, [hydrate]);

  useEffect(() => {
    // Short boot cue — do not artificially delay the page for over a second
    const t = window.setTimeout(() => setBootReady(true), 180);
    return () => window.clearTimeout(t);
  }, []);

  const visible = useMemo(() => {
    if (tab === "saved") {
      // Saved = checked matches
      return matches.filter((m) => m.status === "viewed" || pendingSaved.has(m.parcel_id));
    }
    // Matches = new + current. Opening a report does not remove them.
    // Checked items stay greyed here this session, then live under Saved after refresh.
    return matches.filter(
      (m) => m.status === "new" || m.status === "unseen" || pendingSaved.has(m.parcel_id),
    );
  }, [matches, tab, pendingSaved]);

  const matchesTabCount = useMemo(
    () =>
      matches.filter(
        (m) => m.status === "new" || m.status === "unseen" || pendingSaved.has(m.parcel_id),
      ).length,
    [matches, pendingSaved],
  );
  const savedTabCount = useMemo(() => {
    const ids = new Set<string>();
    for (const m of matches) {
      if (m.status === "viewed" || pendingSaved.has(m.parcel_id)) ids.add(m.parcel_id);
    }
    return ids.size;
  }, [matches, pendingSaved]);

  async function toggleSeen(parcelId: string, nextChecked: boolean) {
    setPendingSaved((prev) => {
      const next = new Set(prev);
      if (nextChecked) next.add(parcelId);
      else next.delete(parcelId);
      const openIds = matches
        .filter((m) => m.status === "new" || m.status === "unseen" || next.has(m.parcel_id))
        .map((m) => m.parcel_id);
      const unique = Array.from(new Set(openIds));
      setMarkAllActive(unique.length > 0 && unique.every((id) => next.has(id)));
      return next;
    });
    setMatches((prev) =>
      prev.map((m) => {
        if (m.parcel_id !== parcelId) return m;
        if (nextChecked) return { ...m, status: "viewed" };
        // Restore to unseen (or new if it was a discovery)
        return { ...m, status: m.is_new_discovery || m.origin === "new_discovery" ? "new" : "unseen" };
      }),
    );
    setCounts((c) => {
      const delta = nextChecked ? 1 : -1;
      return {
        ...c,
        viewed: Math.max(0, c.viewed + delta),
        unseen: Math.max(0, (c.unseen || 0) + (nextChecked ? -1 : 1)),
      };
    });
    try {
      if (nextChecked) await landsignalApi.markLandAlertViewed(parcelId);
      else await landsignalApi.unmarkLandAlertViewed(parcelId);
    } catch {
      /* local toggle still applied; sync on next load */
    }
  }

  const markAllTargetCount = useMemo(
    () => matches.filter((m) => m.status === "new" || m.status === "unseen").length,
    [matches],
  );

  // Undo when this session saved all, OR everything already sits in Saved (e.g. after refresh)
  const showUndoMarkAll =
    markAllActive ||
    pendingSaved.size > 0 ||
    (savedTabCount > 0 && markAllTargetCount === 0);

  async function toggleMarkAllSeen() {
    if (showUndoMarkAll) {
      setMarkAllActive(false);
      setPendingSaved(new Set());
      try {
        await landsignalApi.markAllLandAlertsUnseen(profileId || undefined);
      } catch {
        const savedIds = matches.filter((m) => m.status === "viewed").map((m) => m.parcel_id);
        await Promise.all(
          savedIds.map((id) => landsignalApi.unmarkLandAlertViewed(id).catch(() => null)),
        );
      }
      const data = await landsignalApi.landAlertMatches(profileId || undefined);
      setMatches(data.matches || []);
      setCounts(data.counts || { new: 0, unseen: 0, viewed: 0, total: 0 });
      setTab("matches");
      setMsg("");
      return;
    }

    const ids = matches
      .filter((m) => m.status === "new" || m.status === "unseen")
      .map((m) => m.parcel_id);
    if (!ids.length) return;
    setMarkAllActive(true);
    setPendingSaved(new Set(ids));
    try {
      await landsignalApi.markAllLandAlertsSeen(profileId || undefined);
    } catch {
      await Promise.all(ids.map((id) => landsignalApi.markLandAlertViewed(id).catch(() => null)));
    }
    setMatches((prev) =>
      prev.map((m) => (ids.includes(m.parcel_id) ? { ...m, status: "viewed" } : m)),
    );
    setCounts((c) => ({
      ...c,
      new: 0,
      unseen: 0,
      viewed: c.total,
    }));
  }

  async function saveProfile() {
    setSaving(true);
    setMsg("");
    try {
      const states = form.states
        .split(/[,;\s]+/)
        .map((s) => s.trim().toUpperCase())
        .filter((s) => s.length === 2);
      const body = {
        id: profileId || undefined,
        name: form.name || "My Land Alert",
        preferences: {
          states,
          states_mode: form.states_mode,
          budget_min: parseNum(form.budget_min),
          budget_max: parseNum(form.budget_max),
          budget_mode: form.budget_mode,
          acres_min: parseNum(form.acres_min),
          acres_max: parseNum(form.acres_max),
          acres_mode: form.acres_mode,
          strategies: form.strategies,
          land_types: form.land_types.map((t) => t.toLowerCase()),
          hold_years_min: parseNum(form.hold_years_min),
          hold_years_max: parseNum(form.hold_years_max),
          desired_return_pct: parseNum(form.desired_return_pct),
          max_risk: form.max_risk,
          interests: form.interests,
          infrastructure_prefs: form.infrastructure_prefs,
        },
        notify: {
          email: form.email,
          sms: form.sms,
          in_app: form.in_app,
          push: form.push,
          sensitivity: form.sensitivity,
          frequency: form.frequency,
          email_address: form.email_address,
          phone: form.phone,
        },
      };
      const res = await landsignalApi.upsertLandAlertProfile(body);
      setProfileId(String(res.profile.id));
      setPaused(Boolean(res.profile.paused));
      setHasProfile(true);
      setEditing(false);
      setMatches(res.matches || []);
      setCounts({
        new: res.new_count || 0,
        unseen: (res.match_count || 0) - (res.new_count || 0),
        viewed: 0,
        total: res.match_count || 0,
      });
      await loadMatches();
      setMsg(
        `Profile saved. ${res.match_count} current matches from existing inventory. Monitoring continues in the background.`,
      );
      setTab("matches");
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Could not save profile");
    } finally {
      setSaving(false);
    }
  }

  async function togglePause() {
    if (!profileId) return;
    if (paused) {
      await landsignalApi.resumeLandAlert(profileId);
      setPaused(false);
      setMsg("Land Alerts resumed — monitoring active.");
    } else {
      await landsignalApi.pauseLandAlert(profileId);
      setPaused(true);
      setMsg("Land Alerts paused. Existing matches stay visible; no new notifications.");
    }
    await loadMatches();
  }

  function toggleStrategy(id: string) {
    setForm((f) => ({
      ...f,
      strategies: f.strategies.includes(id) ? f.strategies.filter((x) => x !== id) : [...f.strategies, id],
    }));
  }

  function toggleLandType(t: string) {
    setForm((f) => ({
      ...f,
      land_types: f.land_types.includes(t) ? f.land_types.filter((x) => x !== t) : [...f.land_types, t],
    }));
  }

  const selectedStates = useMemo(() => parseStates(form.states), [form.states]);
  const budgetPresetId = budgetCustomOpen
    ? "custom"
    : matchPreset(BUDGET_PRESETS, form.budget_min, form.budget_max);
  const acrePresetId = acresCustomOpen
    ? "custom"
    : matchPreset(ACRE_PRESETS, form.acres_min, form.acres_max);
  const holdPresetId = holdCustomOpen
    ? "custom"
    : matchPreset(HOLD_PRESETS, form.hold_years_min, form.hold_years_max);
  const returnPreset =
    RETURN_PRESETS.find((p) => p.value === form.desired_return_pct)?.id ||
    (form.desired_return_pct ? "custom" : "any");
  const strategiesAll =
    form.strategies.length === ALL_STRATEGY_IDS.length &&
    ALL_STRATEGY_IDS.every((id) => form.strategies.includes(id));
  const landTypesAll =
    form.land_types.length === LAND_TYPE_OPTS.length &&
    LAND_TYPE_OPTS.every((t) => form.land_types.includes(t));
  const interestsAll = ALL_INTEREST_KEYS.every((key) => form.interests[key]);
  const infraAll =
    form.infrastructure_prefs.length === ALL_INFRA_IDS.length &&
    ALL_INFRA_IDS.every((id) => form.infrastructure_prefs.includes(id));

  const profileSummary = useMemo(() => {
    const bits: string[] = [];
    if (!selectedStates.length) bits.push("All states");
    else if (selectedStates.length <= 4) bits.push(selectedStates.join(", "));
    else bits.push(`${selectedStates.length} states`);
    if (form.budget_max) bits.push(`≤ $${Number(form.budget_max).toLocaleString()}`);
    else if (form.budget_min) bits.push(`≥ $${Number(form.budget_min).toLocaleString()}`);
    if (form.acres_min) bits.push(`${form.acres_min}+ ac`);
    if (form.strategies.length) bits.push(form.strategies.length === 1 ? STRATEGY_OPTS.find((s) => s.id === form.strategies[0])?.label || "1 strategy" : `${form.strategies.length} strategies`);
    bits.push(RISK_OPTS.find((r) => r.id === form.max_risk)?.label || "Moderate");
    return bits.join(" · ");
  }, [selectedStates, form.budget_max, form.budget_min, form.acres_min, form.strategies, form.max_risk]);

  function setStatesList(next: string[]) {
    const unique = Array.from(new Set(next.map((s) => s.toUpperCase()))).sort();
    setForm((f) => ({ ...f, states: unique.join(", ") }));
  }

  function toggleState(code: string) {
    const set = new Set(selectedStates);
    if (set.has(code)) set.delete(code);
    else set.add(code);
    setStatesList([...set]);
  }

  function toggleRegion(states: string[]) {
    const haveAll = states.every((s) => selectedStates.includes(s));
    if (haveAll) setStatesList(selectedStates.filter((s) => !states.includes(s)));
    else setStatesList([...new Set([...selectedStates, ...states])]);
  }

  if (loading || !bootReady) {
    return (
      <div className="land-alerts-page space-y-4">
        <div className="land-alerts-topbar">
          <Link href="/" className="land-alerts-back">
            ← Back
          </Link>
          <div className="land-alerts-live" title="LandSignal is scanning live">
            <LiveMagnifier size={28} />
            <span>Scanning live</span>
          </div>
        </div>
        <LandAlertsLoader />
      </div>
    );
  }

  return (
    <div className="land-alerts-page space-y-6">
      <div className="land-alerts-topbar">
        <Link href="/" className="land-alerts-back">
          ← Back
        </Link>
        <div className="land-alerts-live" title="LandSignal is scanning live">
          <LiveMagnifier size={28} />
          <span>Scanning live</span>
        </div>
      </div>
      <div className="land-alerts-hero">
        <div>
          <h1 className="display text-3xl font-semibold">Land Alerts</h1>
          <p className="mt-1 max-w-2xl text-sm text-[var(--muted)]">
            Tell LandSignal what kind of land you want once. We watch public markets in the background,
            score opportunities, and alert you when something deserves attention — even when this tab is
            closed. This is separate from homepage <strong>Show matches</strong> search filters.
          </p>
        </div>
        {hasProfile ? (
          <div className="land-alerts-hero-actions">
            <button type="button" className="btn btn-ghost" onClick={() => setEditing((e) => !e)}>
              {editing ? "Close editor" : "Edit Preferences"}
            </button>
            <button type="button" className="btn btn-ghost" onClick={() => void togglePause()}>
              {paused ? "Resume Alerts" : "Pause Alerts"}
            </button>
            <button
              type="button"
              className={`btn btn-ghost${showUndoMarkAll ? " is-mark-all-on" : ""}`}
              disabled={!showUndoMarkAll && markAllTargetCount === 0}
              onClick={() => void toggleMarkAllSeen()}
              aria-pressed={showUndoMarkAll}
            >
              {showUndoMarkAll ? "Unsave all" : "Save all"}
            </button>
          </div>
        ) : null}
      </div>

      {msg ? <div className="land-alerts-msg">{msg}</div> : null}

      {hasProfile && !editing ? (
        <div className="land-alerts-status panel p-4">
          <div className="land-alerts-status-row">
            <div>
              <div className="display text-lg font-semibold">{form.name}</div>
              <div className="text-sm text-[var(--muted)]">
                {paused ? "Paused — not monitoring new listings" : "Active — monitoring continuously"}
                {form.states ? ` · States: ${form.states.toUpperCase()}` : ""}
                {form.budget_max ? ` · Budget up to $${Number(form.budget_max).toLocaleString()}` : ""}
              </div>
            </div>
            <div className="land-alerts-new-count">
              {counts.new > 0 ? `${counts.new} New Match${counts.new === 1 ? "" : "es"}` : "No new matches"}
            </div>
          </div>
        </div>
      ) : null}

      {editing ? (
        <section className="acq-profile panel">
          <header className="acq-profile-head">
            <div>
              <h2 className="display text-xl font-semibold">Acquisition profile</h2>
              <p className="mt-1 text-sm text-[var(--muted)]">
                Tap to set preferences. Use Must only for hard constraints — Prefer and Flexible keep near-misses.
              </p>
            </div>
            <p className="acq-profile-summary" aria-live="polite">
              {profileSummary}
            </p>
          </header>

          <div className="acq-section">
            <div className="acq-section-label">Profile name</div>
            <div className="land-alert-chips">
              {PROFILE_NAME_PRESETS.map((name) => (
                <button
                  key={name}
                  type="button"
                  className={`land-alert-chip${form.name === name ? " on" : ""}`}
                  onClick={() => setForm((f) => ({ ...f, name }))}
                >
                  {name}
                </button>
              ))}
            </div>
            <label className="land-alert-field acq-optional-input">
              <span>Or rename</span>
              <input
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                placeholder="My Land Alert"
              />
            </label>
          </div>

          <div className="acq-section">
            <div className="acq-section-top">
              <div>
                <div className="acq-section-label">Where</div>
                <p className="acq-section-hint">None selected = watch all states</p>
              </div>
              <ModeToggle
                value={form.states_mode}
                onChange={(m) => setForm((f) => ({ ...f, states_mode: m }))}
              />
            </div>
            <div className="land-alert-chips">
              <button
                type="button"
                className={`land-alert-chip${!selectedStates.length ? " on" : ""}`}
                onClick={() => setStatesList([])}
              >
                All U.S.
              </button>
              {STATE_REGIONS.map((region) => {
                const active = region.states.every((s) => selectedStates.includes(s));
                const partial = !active && region.states.some((s) => selectedStates.includes(s));
                return (
                  <button
                    key={region.id}
                    type="button"
                    className={`land-alert-chip${active ? " on" : ""}${partial ? " is-partial" : ""}`}
                    onClick={() => toggleRegion(region.states)}
                  >
                    {region.label}
                  </button>
                );
              })}
            </div>
            <div className="acq-state-grid" role="group" aria-label="States">
              {ALL_STATES.map((code) => (
                <button
                  key={code}
                  type="button"
                  className={`acq-state${selectedStates.includes(code) ? " on" : ""}`}
                  aria-pressed={selectedStates.includes(code)}
                  onClick={() => toggleState(code)}
                >
                  {code}
                </button>
              ))}
            </div>
          </div>

          <div className="acq-section">
            <div className="acq-section-top">
              <div className="acq-section-label">Budget</div>
              <ModeToggle
                value={form.budget_mode}
                onChange={(m) => setForm((f) => ({ ...f, budget_mode: m }))}
              />
            </div>
            <div className="land-alert-chips acq-chips-tight">
              {BUDGET_PRESETS.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  className={`land-alert-chip${budgetPresetId === p.id ? " on" : ""}`}
                  onClick={() => {
                    if (p.id === "custom") {
                      setBudgetCustomOpen(true);
                      return;
                    }
                    setBudgetCustomOpen(false);
                    setForm((f) => ({ ...f, budget_min: p.min, budget_max: p.max }));
                  }}
                >
                  {p.label}
                </button>
              ))}
            </div>
            {budgetPresetId === "custom" ? (
              <div className="acq-range-row">
                <input
                  className="acq-range-input"
                  inputMode="numeric"
                  aria-label="Budget min"
                  value={form.budget_min}
                  placeholder="Min $"
                  onChange={(e) => setForm((f) => ({ ...f, budget_min: e.target.value.replace(/[^\d]/g, "") }))}
                />
                <span className="acq-range-sep" aria-hidden>
                  –
                </span>
                <input
                  className="acq-range-input"
                  inputMode="numeric"
                  aria-label="Budget max"
                  value={form.budget_max}
                  placeholder="Max $"
                  onChange={(e) => setForm((f) => ({ ...f, budget_max: e.target.value.replace(/[^\d]/g, "") }))}
                />
              </div>
            ) : null}
          </div>

          <div className="acq-section">
            <div className="acq-section-top">
              <div className="acq-section-label">Acreage</div>
              <ModeToggle
                value={form.acres_mode}
                onChange={(m) => setForm((f) => ({ ...f, acres_mode: m }))}
              />
            </div>
            <div className="land-alert-chips acq-chips-tight">
              {ACRE_PRESETS.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  className={`land-alert-chip${acrePresetId === p.id ? " on" : ""}`}
                  onClick={() => {
                    if (p.id === "custom") {
                      setAcresCustomOpen(true);
                      return;
                    }
                    setAcresCustomOpen(false);
                    setForm((f) => ({ ...f, acres_min: p.min, acres_max: p.max }));
                  }}
                >
                  {p.label}
                </button>
              ))}
            </div>
            {acrePresetId === "custom" ? (
              <div className="acq-range-row">
                <input
                  className="acq-range-input"
                  inputMode="decimal"
                  aria-label="Acres min"
                  value={form.acres_min}
                  placeholder="Min ac"
                  onChange={(e) => setForm((f) => ({ ...f, acres_min: e.target.value.replace(/[^\d.]/g, "") }))}
                />
                <span className="acq-range-sep" aria-hidden>
                  –
                </span>
                <input
                  className="acq-range-input"
                  inputMode="decimal"
                  aria-label="Acres max"
                  value={form.acres_max}
                  placeholder="Max ac"
                  onChange={(e) => setForm((f) => ({ ...f, acres_max: e.target.value.replace(/[^\d.]/g, "") }))}
                />
              </div>
            ) : null}
          </div>

          <div className="acq-section">
            <div className="acq-section-label">Strategy & land type</div>
            <div className="land-alert-chips acq-chips-tight">
              <button
                type="button"
                className={`land-alert-chip${strategiesAll ? " on" : ""}`}
                aria-pressed={strategiesAll}
                onClick={() =>
                  setForm((f) => ({
                    ...f,
                    strategies: strategiesAll ? [] : [...ALL_STRATEGY_IDS],
                  }))
                }
              >
                Any
              </button>
              {STRATEGY_OPTS.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  className={`land-alert-chip${form.strategies.includes(s.id) ? " on" : ""}`}
                  onClick={() => toggleStrategy(s.id)}
                >
                  {s.label}
                </button>
              ))}
            </div>
            <div className="land-alert-chips acq-chips-tight acq-chips-gap">
              <button
                type="button"
                className={`land-alert-chip${landTypesAll ? " on" : ""}`}
                aria-pressed={landTypesAll}
                onClick={() =>
                  setForm((f) => ({
                    ...f,
                    land_types: landTypesAll ? [] : [...LAND_TYPE_OPTS],
                  }))
                }
              >
                Any
              </button>
              {LAND_TYPE_OPTS.map((t) => (
                <button
                  key={t}
                  type="button"
                  className={`land-alert-chip${form.land_types.includes(t) ? " on" : ""}`}
                  onClick={() => toggleLandType(t)}
                >
                  {t}
                </button>
              ))}
            </div>
          </div>

          <div className="acq-section">
            <div className="acq-section-label">Hold & return</div>
            <div className="land-alert-chips acq-chips-tight">
              {HOLD_PRESETS.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  className={`land-alert-chip${holdPresetId === p.id ? " on" : ""}`}
                  onClick={() => {
                    if (p.id === "custom") {
                      setHoldCustomOpen(true);
                      return;
                    }
                    setHoldCustomOpen(false);
                    setForm((f) => ({ ...f, hold_years_min: p.min, hold_years_max: p.max }));
                  }}
                >
                  {p.label}
                </button>
              ))}
            </div>
            {holdPresetId === "custom" ? (
              <div className="acq-range-row">
                <input
                  className="acq-range-input"
                  inputMode="numeric"
                  aria-label="Hold years min"
                  value={form.hold_years_min}
                  placeholder="Min yrs"
                  onChange={(e) => setForm((f) => ({ ...f, hold_years_min: e.target.value.replace(/[^\d]/g, "") }))}
                />
                <span className="acq-range-sep" aria-hidden>
                  –
                </span>
                <input
                  className="acq-range-input"
                  inputMode="numeric"
                  aria-label="Hold years max"
                  value={form.hold_years_max}
                  placeholder="Max yrs"
                  onChange={(e) => setForm((f) => ({ ...f, hold_years_max: e.target.value.replace(/[^\d]/g, "") }))}
                />
              </div>
            ) : null}
            <div className="land-alert-chips acq-chips-tight acq-chips-gap">
              {RETURN_PRESETS.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  className={`land-alert-chip${returnPreset === p.id ? " on" : ""}`}
                  onClick={() => setForm((f) => ({ ...f, desired_return_pct: p.value }))}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>

          <div className="acq-section">
            <div className="acq-section-label">Max risk</div>
            <div className="acq-segment" role="radiogroup" aria-label="Maximum acceptable risk">
              {RISK_OPTS.map((r) => (
                <button
                  key={r.id}
                  type="button"
                  className={`acq-segment-btn${form.max_risk === r.id ? " on" : ""}`}
                  aria-pressed={form.max_risk === r.id}
                  onClick={() => setForm((f) => ({ ...f, max_risk: r.id }))}
                >
                  {r.label}
                </button>
              ))}
            </div>
          </div>

          <div className="acq-section">
            <div className="acq-section-label">Interests</div>
            <div className="land-alert-chips acq-chips-tight">
              <button
                type="button"
                className={`land-alert-chip${interestsAll ? " on" : ""}`}
                aria-pressed={interestsAll}
                onClick={() =>
                  setForm((f) => {
                    const next = { ...f.interests };
                    for (const key of ALL_INTEREST_KEYS) next[key] = !interestsAll;
                    return { ...f, interests: next };
                  })
                }
              >
                Any
              </button>
              {INTEREST_OPTS.map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  className={`land-alert-chip${form.interests[key] ? " on" : ""}`}
                  aria-pressed={form.interests[key]}
                  onClick={() =>
                    setForm((f) => ({
                      ...f,
                      interests: { ...f.interests, [key]: !f.interests[key] },
                    }))
                  }
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          <div className="acq-section">
            <div className="acq-section-label acq-label-with-tip">
              <span>Infrastructure</span>
              <HelpTip
                tone="panel"
                title="What these mean"
                body="Road access = legal/physical road frontage or deeded easement potential. Utilities = electric/water/sewer available or nearby. Power nearby = transmission or distribution close enough for service or energy projects. Water access = surface water, irrigation, or well potential. Tap Any for no infrastructure preference."
              />
            </div>
            <div className="land-alert-chips acq-chips-tight">
              <button
                type="button"
                className={`land-alert-chip${infraAll ? " on" : ""}`}
                aria-pressed={infraAll}
                onClick={() =>
                  setForm((f) => ({
                    ...f,
                    infrastructure_prefs: infraAll ? [] : [...ALL_INFRA_IDS],
                  }))
                }
              >
                Any
              </button>
              {INFRA_OPTS.map(([id, label]) => {
                const on = form.infrastructure_prefs.includes(id);
                return (
                  <button
                    key={id}
                    type="button"
                    className={`land-alert-chip${on ? " on" : ""}`}
                    aria-pressed={on}
                    onClick={() =>
                      setForm((f) => ({
                        ...f,
                        infrastructure_prefs: on
                          ? f.infrastructure_prefs.filter((x) => x !== id)
                          : [...f.infrastructure_prefs, id],
                      }))
                    }
                  >
                    {label}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="acq-section acq-notify">
            <div className="acq-section-label">Notifications</div>
            <p className="acq-section-hint">Discovery keeps running — these only change how you hear about it</p>
            <div className="acq-switch-grid">
              <SwitchToggle
                checked={form.in_app}
                onChange={(v) => setForm((f) => ({ ...f, in_app: v }))}
                label="In-app"
                hint="Bell & Recent feed"
              />
              <SwitchToggle
                checked={form.email}
                onChange={(v) => setForm((f) => ({ ...f, email: v }))}
                label="Email"
                hint={form.email && !form.email_address ? "Add address below" : "When SMTP is configured"}
              />
              <SwitchToggle
                checked={form.sms}
                onChange={(v) => setForm((f) => ({ ...f, sms: v }))}
                label="SMS"
                hint={form.sms && !form.phone ? "Add phone below" : "When Twilio is configured"}
              />
              <SwitchToggle
                checked={form.push}
                onChange={(v) => setForm((f) => ({ ...f, push: v }))}
                label="Browser push"
                hint="When push is configured"
              />
            </div>

            <div className="acq-section-label acq-sublabel">Sensitivity</div>
            <div className="land-alert-chips">
              {SENSITIVITY_OPTS.map((o) => (
                <button
                  key={o.id}
                  type="button"
                  className={`land-alert-chip${form.sensitivity === o.id ? " on" : ""}`}
                  onClick={() => setForm((f) => ({ ...f, sensitivity: o.id }))}
                >
                  {o.label}
                </button>
              ))}
            </div>

            <div className="acq-section-label acq-sublabel">Frequency</div>
            <div className="land-alert-chips">
              {FREQUENCY_OPTS.map((o) => (
                <button
                  key={o.id}
                  type="button"
                  className={`land-alert-chip${form.frequency === o.id ? " on" : ""}`}
                  onClick={() => setForm((f) => ({ ...f, frequency: o.id }))}
                >
                  {o.label}
                </button>
              ))}
            </div>

            {(form.email || form.sms) && (
              <div className="acq-range-row acq-chips-gap">
                {form.email ? (
                  <label className="land-alert-field">
                    <span>Email address</span>
                    <input
                      type="email"
                      value={form.email_address}
                      placeholder="you@example.com"
                      onChange={(e) => setForm((f) => ({ ...f, email_address: e.target.value }))}
                    />
                  </label>
                ) : null}
                {form.sms ? (
                  <label className="land-alert-field">
                    <span>Phone</span>
                    <input
                      type="tel"
                      value={form.phone}
                      placeholder="+1…"
                      onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))}
                    />
                  </label>
                ) : null}
              </div>
            )}
          </div>

          <div className="acq-actions">
            <button type="button" className="btn btn-dark" disabled={saving} onClick={() => void saveProfile()}>
              {saving ? "Saving & matching…" : hasProfile ? "Save & recalculate matches" : "Start Land Alerts"}
            </button>
            {hasProfile ? (
              <button type="button" className="btn btn-ghost" onClick={() => setEditing(false)}>
                Cancel
              </button>
            ) : null}
          </div>
        </section>
      ) : null}

      {hasProfile ? (
        <section className="space-y-4">
          <div className="land-alerts-tabs">
            <button
              type="button"
              className={tab === "matches" ? "on" : ""}
              onClick={() => setTab("matches")}
            >
              Matches ({matchesTabCount})
            </button>
            <button
              type="button"
              className={tab === "saved" ? "on" : ""}
              onClick={() => setTab("saved")}
            >
              Saved ({savedTabCount})
            </button>
          </div>

          <div className="space-y-3">
            {visible.map((row) => (
              <MatchCard
                key={row.id}
                row={row}
                dimmed={pendingSaved.has(row.parcel_id) || row.status === "viewed"}
                onToggleSeen={toggleSeen}
              />
            ))}
            {!visible.length ? (
              <div className="panel empty-state p-6">
                {tab === "saved"
                  ? "No saved matches yet. Check a match to save it here."
                  : "No matches for this profile yet. Widen preferences or wait for new inventory."}
              </div>
            ) : null}
          </div>
        </section>
      ) : null}

      {inAppAlerts.length ? (
        <section className="space-y-3">
          <h2 className="display text-xl font-semibold">Recent notifications</h2>
          {inAppAlerts.map((a) => {
            const body = (a.body || {}) as Record<string, unknown>;
            const link = String(body.deep_link || (a.parcel_id ? `/parcels/${a.parcel_id}` : "/alerts"));
            const scouted = formatScoutedAt(a);
            return (
              <Link key={String(a.id)} href={link} className="land-alert-notif panel block p-4">
                <div className="land-alert-notif-head">
                  <div className="font-medium">{String(a.title || "Land Alert")}</div>
                  {scouted ? (
                    <time className="land-alert-notif-time" dateTime={String(body.scouted_at || body.retrieved_at || a.created_at || "")}>
                      {scouted}
                    </time>
                  ) : null}
                </div>
                <div className="mt-1 text-sm text-[var(--muted)]">
                  {String(body.summary || "")}
                </div>
              </Link>
            );
          })}
        </section>
      ) : null}
    </div>
  );
}
