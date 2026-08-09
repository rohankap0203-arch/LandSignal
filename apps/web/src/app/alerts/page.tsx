"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AcquireRail } from "@/components/acquire-rail";
import { LandAlertsLoader } from "@/components/land-alerts-loader";
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
  { id: "LAND_BANK", label: "Land banking / speculation" },
  { id: "FARMLAND", label: "Agricultural / farmland" },
  { id: "DEVELOPMENT", label: "Development" },
  { id: "RECREATIONAL", label: "Recreational" },
  { id: "TIMBER", label: "Timber / natural resources" },
  { id: "ENERGY", label: "Energy" },
];

const LAND_TYPE_OPTS = ["Vacant", "Raw land", "Farmland", "Timber", "Recreational", "Residential lot", "Commercial"];

function parseNum(v: string): number | undefined {
  const n = Number(String(v).replace(/[$,\s]/g, ""));
  return Number.isFinite(n) ? n : undefined;
}

function ModeSelect({
  value,
  onChange,
}: {
  value: PrefMode;
  onChange: (m: PrefMode) => void;
}) {
  return (
    <select
      className="land-alert-mode"
      value={value}
      onChange={(e) => onChange(e.target.value as PrefMode)}
      aria-label="Preference strength"
    >
      <option value="must">Must have</option>
      <option value="prefer">Prefer</option>
      <option value="flexible">Flexible</option>
    </select>
  );
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
  const href = row.deep_link || `/parcels/${row.parcel_id}`;

  function flipToggle() {
    setFlipped((v) => !v);
  }

  return (
    <div
      className={`land-alert-flip${flipped ? " is-flipped" : ""}${row.status === "new" && !dimmed ? " is-new" : ""}${dimmed ? " is-dimmed" : ""}`}
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
                title="Mark as seen — moves to Viewed after refresh"
                onClick={(e) => e.stopPropagation()}
                onKeyDown={(e) => e.stopPropagation()}
              >
                <input
                  type="checkbox"
                  checked={dimmed}
                  onChange={(e) => onToggleSeen(row.parcel_id, e.target.checked)}
                  aria-label="Mark match as seen"
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
            <span>{row.asking_price_display}</span>
            <span>{row.acres_display}</span>
            <span>{row.price_per_acre_display}</span>
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
            <div className="land-alert-card-title">{row.property_name}</div>
            <div className="land-alert-card-meta">
              <span>{row.location || row.state || "—"}</span>
              <span>{row.asking_price_display}</span>
              <span>{row.acres_display}</span>
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

          <div className="land-alert-back-actions" onClick={(e) => e.stopPropagation()}>
            <Link href={href} className="btn-intel">
              Open full LandSignal report
            </Link>
          </div>
        </article>
      </div>
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
  const [tab, setTab] = useState<"new" | "current" | "viewed">("current");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");
  const [inAppAlerts, setInAppAlerts] = useState<Record<string, unknown>[]>([]);
  /** Checked this session — grey out now; move to Viewed on refresh / return */
  const [pendingSeen, setPendingSeen] = useState<Set<string>>(() => new Set());
  const [markAllActive, setMarkAllActive] = useState(false);
  const [bootReady, setBootReady] = useState(false);

  const loadMatches = useCallback(async () => {
    const data = await landsignalApi.landAlertMatches(profileId || undefined);
    setMatches(data.matches || []);
    setCounts(data.counts || { new: 0, unseen: 0, viewed: 0, total: 0 });
    setPendingSeen(new Set());
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
        setForm({
          ...DEFAULT_FORM,
          name: String(p.name || "My Land Alert"),
          states: Array.isArray(prefs.states) ? (prefs.states as string[]).join(", ") : "",
          states_mode: (prefs.states_mode as PrefMode) || "must",
          budget_min: prefs.budget_min != null ? String(prefs.budget_min) : "",
          budget_max: prefs.budget_max != null ? String(prefs.budget_max) : "",
          budget_mode: (prefs.budget_mode as PrefMode) || "prefer",
          acres_min: prefs.acres_min != null ? String(prefs.acres_min) : "",
          acres_max: prefs.acres_max != null ? String(prefs.acres_max) : "",
          acres_mode: (prefs.acres_mode as PrefMode) || "prefer",
          strategies: Array.isArray(prefs.strategies) ? (prefs.strategies as string[]) : ["LAND_BANK"],
          land_types: Array.isArray(prefs.land_types) ? (prefs.land_types as string[]) : [],
          hold_years_min: prefs.hold_years_min != null ? String(prefs.hold_years_min) : "",
          hold_years_max: prefs.hold_years_max != null ? String(prefs.hold_years_max) : "",
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
      }
      const m = await landsignalApi.landAlertMatches(
        data.has_profile && data.profile ? String((data.profile as { id: string }).id) : undefined,
      );
      setMatches(m.matches || []);
      setCounts(m.counts || { new: 0, unseen: 0, viewed: 0, total: 0 });
      const alerts = await landsignalApi.alerts().catch(() => []);
      setInAppAlerts(
        (alerts || []).filter((a) => String((a as { severity?: string }).severity) === "LAND_ALERT").slice(0, 12),
      );
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
    // Brief distinguished boot visual even on fast loads
    const t = window.setTimeout(() => setBootReady(true), 1100);
    return () => window.clearTimeout(t);
  }, []);

  const visible = useMemo(() => {
    if (tab === "viewed") {
      // Pending checks stay out of Viewed until refresh / return
      return matches.filter((m) => m.status === "viewed" && !pendingSeen.has(m.parcel_id));
    }
    // Keep pending-seen cards in place (greyed) until refresh / return
    if (tab === "new") {
      return matches.filter((m) => m.status === "new" || pendingSeen.has(m.parcel_id));
    }
    return matches.filter(
      (m) => m.status === "new" || m.status === "unseen" || pendingSeen.has(m.parcel_id),
    );
  }, [matches, tab, pendingSeen]);

  async function toggleSeen(parcelId: string, nextChecked: boolean) {
    setPendingSeen((prev) => {
      const next = new Set(prev);
      if (nextChecked) next.add(parcelId);
      else next.delete(parcelId);
      const activeIds = matches
        .filter((m) => m.status === "new" || m.status === "unseen" || next.has(m.parcel_id))
        .map((m) => m.parcel_id);
      const unique = Array.from(new Set(activeIds));
      setMarkAllActive(unique.length > 0 && unique.every((id) => next.has(id)));
      return next;
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

  // Undo when this session marked all, OR everything already sits in Viewed (e.g. after refresh)
  const showUndoMarkAll =
    markAllActive ||
    pendingSeen.size > 0 ||
    (counts.viewed > 0 && markAllTargetCount === 0);

  async function toggleMarkAllSeen() {
    if (showUndoMarkAll) {
      setMarkAllActive(false);
      setPendingSeen(new Set());
      try {
        await landsignalApi.markAllLandAlertsUnseen(profileId || undefined);
      } catch {
        const viewedIds = matches.filter((m) => m.status === "viewed").map((m) => m.parcel_id);
        await Promise.all(
          viewedIds.map((id) => landsignalApi.unmarkLandAlertViewed(id).catch(() => null)),
        );
      }
      // Reload so restored matches leave Viewed and return to New / Current
      const data = await landsignalApi.landAlertMatches(profileId || undefined);
      setMatches(data.matches || []);
      setCounts(data.counts || { new: 0, unseen: 0, viewed: 0, total: 0 });
      setTab("current");
      setMsg("Mark all undone — matches restored to New / Current.");
      return;
    }

    const ids = matches
      .filter((m) => m.status === "new" || m.status === "unseen")
      .map((m) => m.parcel_id);
    if (!ids.length) return;
    setMarkAllActive(true);
    setPendingSeen(new Set(ids));
    try {
      await landsignalApi.markAllLandAlertsSeen(profileId || undefined);
    } catch {
      await Promise.all(ids.map((id) => landsignalApi.markLandAlertViewed(id).catch(() => null)));
    }
    // Keep cards greyed in Current this session; persist viewed for next visit
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
      setTab("current");
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
            closed.
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
              className="btn btn-ghost"
              disabled={!showUndoMarkAll && markAllTargetCount === 0}
              onClick={() => void toggleMarkAllSeen()}
            >
              {showUndoMarkAll ? "Undo mark all" : "Mark all as seen"}
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
        <section className="panel space-y-5 p-5">
          <div>
            <h2 className="display text-xl font-semibold">Acquisition profile</h2>
            <p className="mt-1 text-sm text-[var(--muted)]">
              Preference-driven, not rigid filters. Mark only true constraints as Must have — Prefer and
              Flexible keep strong near-misses in play.
            </p>
          </div>

          <label className="land-alert-field">
            <span>Profile name</span>
            <input value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} />
          </label>

          <div className="land-alert-field-row">
            <label className="land-alert-field grow">
              <span>States / regions (2-letter codes)</span>
              <input
                value={form.states}
                placeholder="e.g. NC, TN, GA"
                onChange={(e) => setForm((f) => ({ ...f, states: e.target.value }))}
              />
            </label>
            <ModeSelect value={form.states_mode} onChange={(m) => setForm((f) => ({ ...f, states_mode: m }))} />
          </div>

          <div className="land-alert-field-row">
            <label className="land-alert-field">
              <span>Budget min</span>
              <input
                value={form.budget_min}
                placeholder="Optional"
                onChange={(e) => setForm((f) => ({ ...f, budget_min: e.target.value }))}
              />
            </label>
            <label className="land-alert-field">
              <span>Budget max</span>
              <input
                value={form.budget_max}
                placeholder="e.g. 250000"
                onChange={(e) => setForm((f) => ({ ...f, budget_max: e.target.value }))}
              />
            </label>
            <ModeSelect value={form.budget_mode} onChange={(m) => setForm((f) => ({ ...f, budget_mode: m }))} />
          </div>

          <div className="land-alert-field-row">
            <label className="land-alert-field">
              <span>Acres min</span>
              <input
                value={form.acres_min}
                placeholder="e.g. 20"
                onChange={(e) => setForm((f) => ({ ...f, acres_min: e.target.value }))}
              />
            </label>
            <label className="land-alert-field">
              <span>Acres max</span>
              <input
                value={form.acres_max}
                placeholder="e.g. 50"
                onChange={(e) => setForm((f) => ({ ...f, acres_max: e.target.value }))}
              />
            </label>
            <ModeSelect value={form.acres_mode} onChange={(m) => setForm((f) => ({ ...f, acres_mode: m }))} />
          </div>

          <div>
            <div className="mb-2 text-sm font-medium">Investment strategy</div>
            <div className="land-alert-chips">
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
          </div>

          <div>
            <div className="mb-2 text-sm font-medium">General land types</div>
            <div className="land-alert-chips">
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

          <div className="grid gap-3 md:grid-cols-3">
            <label className="land-alert-field">
              <span>Hold period min (years)</span>
              <input
                value={form.hold_years_min}
                onChange={(e) => setForm((f) => ({ ...f, hold_years_min: e.target.value }))}
              />
            </label>
            <label className="land-alert-field">
              <span>Hold period max</span>
              <input
                value={form.hold_years_max}
                onChange={(e) => setForm((f) => ({ ...f, hold_years_max: e.target.value }))}
              />
            </label>
            <label className="land-alert-field">
              <span>Desired return % (approx)</span>
              <input
                value={form.desired_return_pct}
                placeholder="e.g. 12"
                onChange={(e) => setForm((f) => ({ ...f, desired_return_pct: e.target.value }))}
              />
            </label>
          </div>

          <label className="land-alert-field">
            <span>Maximum acceptable risk</span>
            <select value={form.max_risk} onChange={(e) => setForm((f) => ({ ...f, max_risk: e.target.value }))}>
              <option value="low">Low</option>
              <option value="moderate">Moderate</option>
              <option value="high">High</option>
              <option value="very_high">Very high</option>
            </select>
          </label>

          <div>
            <div className="mb-2 text-sm font-medium">Interests</div>
            <div className="land-alert-checks">
              {(
                [
                  ["land_banking", "Land banking / speculation"],
                  ["agricultural", "Agricultural / farmland"],
                  ["recreational", "Recreational land"],
                  ["residential_dev", "Residential development"],
                  ["commercial_dev", "Commercial development"],
                  ["timber", "Timber / natural resources"],
                  ["development", "General development"],
                ] as const
              ).map(([key, label]) => (
                <label key={key} className="land-alert-check">
                  <input
                    type="checkbox"
                    checked={form.interests[key]}
                    onChange={(e) =>
                      setForm((f) => ({
                        ...f,
                        interests: { ...f.interests, [key]: e.target.checked },
                      }))
                    }
                  />
                  {label}
                </label>
              ))}
            </div>
          </div>

          <div>
            <div className="mb-2 text-sm font-medium">Infrastructure / access</div>
            <div className="land-alert-checks">
              {[
                ["road_access", "Road access"],
                ["utilities", "Utilities"],
                ["power", "Power nearby"],
                ["water", "Water access"],
              ].map(([id, label]) => (
                <label key={id} className="land-alert-check">
                  <input
                    type="checkbox"
                    checked={form.infrastructure_prefs.includes(id)}
                    onChange={(e) =>
                      setForm((f) => ({
                        ...f,
                        infrastructure_prefs: e.target.checked
                          ? [...f.infrastructure_prefs, id]
                          : f.infrastructure_prefs.filter((x) => x !== id),
                      }))
                    }
                  />
                  {label}
                </label>
              ))}
            </div>
          </div>

          <div className="land-alert-notify">
            <h3 className="display text-lg font-semibold">Notifications</h3>
            <p className="mb-3 text-sm text-[var(--muted)]">
              Discovery keeps running regardless. These controls only change how often you hear about it.
            </p>
            <div className="land-alert-checks">
              <label className="land-alert-check">
                <input
                  type="checkbox"
                  checked={form.in_app}
                  onChange={(e) => setForm((f) => ({ ...f, in_app: e.target.checked }))}
                />
                In-app
              </label>
              <label className="land-alert-check">
                <input
                  type="checkbox"
                  checked={form.email}
                  onChange={(e) => setForm((f) => ({ ...f, email: e.target.checked }))}
                />
                Email
              </label>
              <label className="land-alert-check">
                <input
                  type="checkbox"
                  checked={form.sms}
                  onChange={(e) => setForm((f) => ({ ...f, sms: e.target.checked }))}
                />
                SMS / text
              </label>
              <label className="land-alert-check">
                <input
                  type="checkbox"
                  checked={form.push}
                  onChange={(e) => setForm((f) => ({ ...f, push: e.target.checked }))}
                />
                Browser push (when configured)
              </label>
            </div>
            <div className="mt-3 grid gap-3 md:grid-cols-2">
              <label className="land-alert-field">
                <span>Alert sensitivity</span>
                <select
                  value={form.sensitivity}
                  onChange={(e) => setForm((f) => ({ ...f, sensitivity: e.target.value }))}
                >
                  <option value="exceptional">Exceptional matches only</option>
                  <option value="strong">Strong matches</option>
                  <option value="all">All matches</option>
                </select>
              </label>
              <label className="land-alert-field">
                <span>Notification frequency</span>
                <select
                  value={form.frequency}
                  onChange={(e) => setForm((f) => ({ ...f, frequency: e.target.value }))}
                >
                  <option value="immediate">Immediate</option>
                  <option value="daily_digest">Daily digest</option>
                  <option value="weekly_digest">Weekly digest</option>
                  <option value="in_app_only">In-app only</option>
                </select>
              </label>
              <label className="land-alert-field">
                <span>Email address</span>
                <input
                  value={form.email_address}
                  placeholder="you@example.com"
                  onChange={(e) => setForm((f) => ({ ...f, email_address: e.target.value }))}
                />
              </label>
              <label className="land-alert-field">
                <span>Phone (SMS)</span>
                <input
                  value={form.phone}
                  placeholder="+1…"
                  onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))}
                />
              </label>
            </div>
          </div>

          <div className="flex flex-wrap gap-2">
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
              className={tab === "new" ? "on" : ""}
              onClick={() => setTab("new")}
            >
              New Matches ({counts.new})
            </button>
            <button
              type="button"
              className={tab === "current" ? "on" : ""}
              onClick={() => setTab("current")}
            >
              Current Matches ({counts.new + counts.unseen})
            </button>
            <button
              type="button"
              className={tab === "viewed" ? "on" : ""}
              onClick={() => setTab("viewed")}
            >
              Viewed ({counts.viewed})
            </button>
          </div>

          <div className="space-y-3">
            {visible.map((row) => (
              <MatchCard
                key={row.id}
                row={row}
                dimmed={pendingSeen.has(row.parcel_id)}
                onToggleSeen={toggleSeen}
              />
            ))}
            {!visible.length ? (
              <div className="panel empty-state p-6">
                {tab === "new"
                  ? "No newly discovered matches yet. LandSignal keeps scanning in the background."
                  : tab === "viewed"
                    ? "You haven’t opened any matched properties yet."
                    : "No current matches for this profile. Widen preferences or wait for new inventory."}
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
            return (
              <Link key={String(a.id)} href={link} className="land-alert-notif panel block p-4">
                <div className="font-medium">{String(a.title || "Land Alert")}</div>
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
