"use client";

import { useEffect, useState } from "react";
import { landsignalApi } from "@/lib/api";

type Draft = {
  name: string;
  opportunity_gt: number;
  risk_lt: number;
  confidence_gt: number;
  asymmetry_gt: number;
  channelInApp: boolean;
  channelEmail: boolean;
  channelSms: boolean;
};

const DEFAULT_DRAFT: Draft = {
  name: "My watch rule",
  opportunity_gt: 55,
  risk_lt: 55,
  confidence_gt: 40,
  asymmetry_gt: 50,
  channelInApp: true,
  channelEmail: false,
  channelSms: false,
};

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<Record<string, unknown>[]>([]);
  const [draft, setDraft] = useState<Draft>(DEFAULT_DRAFT);
  const [msg, setMsg] = useState("");
  const [saving, setSaving] = useState(false);

  async function refresh() {
    setAlerts(await landsignalApi.alerts());
  }

  useEffect(() => {
    refresh().catch(() => setAlerts([]));
  }, []);

  async function saveRule() {
    setSaving(true);
    setMsg("");
    try {
      const channels = [
        draft.channelInApp ? "IN_APP" : null,
        draft.channelEmail ? "EMAIL" : null,
        draft.channelSms ? "SMS" : null,
      ].filter(Boolean) as string[];
      await landsignalApi.createAlertRule({
        name: draft.name || "My watch rule",
        predicate: {
          opportunity_gt: draft.opportunity_gt,
          risk_lt: draft.risk_lt,
          confidence_gt: draft.confidence_gt,
          asymmetry_gt: draft.asymmetry_gt,
        },
        channels: channels.length ? channels : ["IN_APP"],
      });
      setMsg("Rule saved. It will fire after the next analysis that meets your toggles.");
      await refresh();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Could not save rule");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="display text-3xl font-semibold">Alerts</h1>
        <p className="mt-1 max-w-2xl text-sm text-[var(--muted)]">
          Set minimum bars for opportunity, risk, and file completeness. When a parcel clears them, you get
          a notice here (email/SMS need SMTP/Twilio configured).
        </p>
      </div>

      <section className="panel grid gap-4 p-5 md:grid-cols-2">
        <label className="text-xs uppercase tracking-wide text-[var(--muted)] md:col-span-2">
          Rule name
          <input
            className="mt-1 w-full rounded-xl border border-[var(--line)] bg-transparent px-3 py-2 text-sm normal-case text-[var(--ink)]"
            value={draft.name}
            onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))}
          />
        </label>

        <Slider
          label="Opportunity score must be at least"
          value={draft.opportunity_gt}
          onChange={(v) => setDraft((d) => ({ ...d, opportunity_gt: v }))}
        />
        <Slider
          label="Risk must stay under"
          value={draft.risk_lt}
          onChange={(v) => setDraft((d) => ({ ...d, risk_lt: v }))}
        />
        <Slider
          label="File-complete score must be at least"
          value={draft.confidence_gt}
          onChange={(v) => setDraft((d) => ({ ...d, confidence_gt: v }))}
        />
        <Slider
          label="Upside vs price must be at least"
          value={draft.asymmetry_gt}
          onChange={(v) => setDraft((d) => ({ ...d, asymmetry_gt: v }))}
        />

        <div className="md:col-span-2">
          <div className="text-xs uppercase tracking-wide text-[var(--muted)]">Notify me via</div>
          <div className="mt-2 flex flex-wrap gap-2">
            {(
              [
                ["channelInApp", "In this app"],
                ["channelEmail", "Email"],
                ["channelSms", "Text / SMS"],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                type="button"
                className={`rounded-full px-3 py-1.5 text-sm border ${
                  draft[key] ? "bg-[var(--brand)] text-white border-[var(--brand)]" : "border-[var(--line)]"
                }`}
                onClick={() => setDraft((d) => ({ ...d, [key]: !d[key] }))}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        <div className="flex flex-wrap gap-2 md:col-span-2">
          <button type="button" className="btn btn-dark" onClick={saveRule} disabled={saving}>
            {saving ? "Saving…" : "Save alert rule"}
          </button>
          <button
            type="button"
            className="btn btn-ghost"
            onClick={() =>
              setDraft({
                ...DEFAULT_DRAFT,
                name: "High-conviction land signal",
                opportunity_gt: 70,
                risk_lt: 40,
                confidence_gt: 55,
                asymmetry_gt: 65,
              })
            }
          >
            Load high-conviction preset
          </button>
          <button type="button" className="btn btn-ghost" onClick={() => setDraft(DEFAULT_DRAFT)}>
            Reset toggles
          </button>
        </div>
        {msg && <div className="md:col-span-2 text-sm text-[var(--warning)]">{msg}</div>}
      </section>

      <section className="space-y-2">
        <h2 className="display text-xl font-semibold">Recent alerts</h2>
        {alerts.map((a) => (
          <div key={String(a.id)} className="panel p-4 text-sm">
            <div className="flex flex-wrap justify-between gap-3">
              <strong>{String(a.title)}</strong>
              <span className="text-[var(--muted)]">{String(a.severity)}</span>
            </div>
            <p className="mt-2 text-[var(--muted)]">
              {typeof a.body === "object" && a.body
                ? String((a.body as AnyBody).summary || (a.body as AnyBody).message || JSON.stringify(a.body))
                : String(a.body || "")}
            </p>
            <div className="mt-2 text-xs text-[var(--muted)]">
              Channels: {((a.delivered_channels as string[]) || []).join(", ") || "—"}
            </div>
          </div>
        ))}
        {!alerts.length && (
          <div className="panel empty-state">No alerts yet. Save a rule, then refresh inventory on Search.</div>
        )}
      </section>
    </div>
  );
}

type AnyBody = { summary?: string; message?: string };

function Slider({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <label className="text-xs uppercase tracking-wide text-[var(--muted)]">
      {label}: <span className="normal-case text-[var(--ink)] font-semibold">{value}</span>
      <input
        type="range"
        min={0}
        max={100}
        value={value}
        className="mt-2 w-full"
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </label>
  );
}
