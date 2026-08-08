"use client";

import Link from "next/link";
import { useState } from "react";
import { landsignalApi } from "@/lib/api";

const STATES = [
  "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA","ME","MD",
  "MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC",
  "SD","TN","TX","UT","VT","VA","WA","WV","WI","WY","DC",
];

export default function IngestPage() {
  const [result, setResult] = useState<{ parcel_id?: string; score_id?: string } | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [step, setStep] = useState(1);
  const [form, setForm] = useState({
    title: "",
    state: "IA",
    county: "",
    apn: "",
    acreage: "40",
    asking_price_usd: "250000",
    latitude: "41.5",
    longitude: "-93.5",
    description: "",
    source_url: "",
  });

  async function submitManual() {
    setBusy(true);
    setError("");
    try {
      const body = {
        ...form,
        acreage: Number(form.acreage),
        asking_price_usd: form.asking_price_usd ? Number(form.asking_price_usd) : null,
        latitude: Number(form.latitude),
        longitude: Number(form.longitude),
        provider_id: "manual",
      };
      const res = (await landsignalApi.ingestManual(body)) as { parcel_id?: string; score_id?: string };
      setResult(res);
      setStep(3);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ingest failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <div>
        <h1 className="display text-3xl font-semibold">Add land</h1>
        <p className="mt-1 text-sm text-[var(--muted)]">
          Paste a private off-market or auction parcel. LandSignal will enrich public screens and score it
          the same way as live inventory.
        </p>
      </div>

      <div className="flex flex-wrap gap-2 text-sm">
        {["Basics", "Location & price", "Review"].map((label, i) => (
          <button
            key={label}
            type="button"
            className={`rounded-full px-3 py-1.5 border ${
              step === i + 1 ? "bg-[var(--brand)] text-white border-[var(--brand)]" : "border-[var(--line)]"
            }`}
            onClick={() => setStep(i + 1)}
          >
            {i + 1}. {label}
          </button>
        ))}
      </div>

      {step === 1 && (
        <section className="panel grid gap-3 p-5 md:grid-cols-2">
          <label className="text-xs uppercase tracking-wide text-[var(--muted)] md:col-span-2">
            Property name / title
            <input
              className="field"
              value={form.title}
              onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
              placeholder="e.g. 80 acres north of Ames"
            />
          </label>
          <label className="text-xs uppercase tracking-wide text-[var(--muted)]">
            State
            <select
              className="field"
              value={form.state}
              onChange={(e) => setForm((f) => ({ ...f, state: e.target.value }))}
            >
              {STATES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs uppercase tracking-wide text-[var(--muted)]">
            County
            <input
              className="field"
              value={form.county}
              onChange={(e) => setForm((f) => ({ ...f, county: e.target.value }))}
            />
          </label>
          <label className="text-xs uppercase tracking-wide text-[var(--muted)] md:col-span-2">
            Short description
            <textarea
              className="field min-h-[88px]"
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            />
          </label>
          <button type="button" className="btn btn-dark md:col-span-2" onClick={() => setStep(2)}>
            Next: location & price
          </button>
        </section>
      )}

      {step === 2 && (
        <section className="panel grid gap-3 p-5 md:grid-cols-2">
          {(
            [
              ["apn", "APN / parcel ID"],
              ["acreage", "Acreage"],
              ["asking_price_usd", "Asking / bid price (blank if unpriced)"],
              ["latitude", "Latitude"],
              ["longitude", "Longitude"],
              ["source_url", "Listing / seller link (optional)"],
            ] as const
          ).map(([key, label]) => (
            <label key={key} className="text-xs uppercase tracking-wide text-[var(--muted)]">
              {label}
              <input
                className="field"
                value={form[key]}
                onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
              />
            </label>
          ))}
          <div className="flex flex-wrap gap-2 md:col-span-2">
            <button type="button" className="btn btn-ghost" onClick={() => setStep(1)}>
              Back
            </button>
            <button type="button" className="btn btn-dark" onClick={() => setStep(3)}>
              Review
            </button>
          </div>
        </section>
      )}

      {step === 3 && (
        <section className="panel space-y-3 p-5">
          <h2 className="display text-xl font-semibold">Review before scoring</h2>
          <dl className="grid gap-2 text-sm md:grid-cols-2">
            {Object.entries(form).map(([k, v]) => (
              <div key={k} className="rounded-xl bg-[var(--bg-soft)] px-3 py-2">
                <dt className="text-[10px] uppercase tracking-wide text-[var(--muted)]">{k}</dt>
                <dd className="font-medium">{v || "—"}</dd>
              </div>
            ))}
          </dl>
          <div className="flex flex-wrap gap-2">
            <button type="button" className="btn btn-ghost" onClick={() => setStep(2)}>
              Back
            </button>
            <button type="button" className="btn btn-dark" onClick={submitManual} disabled={busy}>
              {busy ? "Scoring…" : "Ingest & analyze"}
            </button>
          </div>
          {error && <div className="text-sm text-[var(--danger)]">{error}</div>}
          {result?.parcel_id && (
            <div className="rounded-2xl bg-[var(--bg-soft)] p-4 text-sm">
              Parcel scored.{" "}
              <Link className="font-semibold text-[var(--brand)]" href={`/parcels/${result.parcel_id}`}>
                Open full intelligence →
              </Link>
            </div>
          )}
        </section>
      )}

    </div>
  );
}
