"use client";

import Link from "next/link";
import { useState } from "react";
import { landsignalApi } from "@/lib/api";

const STATES = [
  "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA","ME","MD",
  "MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC",
  "SD","TN","TX","UT","VT","VA","WA","WV","WI","WY","DC",
];

type FormState = {
  title: string;
  state: string;
  county: string;
  apn: string;
  acreage: string;
  asking_price_usd: string;
  latitude: string;
  longitude: string;
  description: string;
  source_url: string;
  address: string;
};

const EMPTY: FormState = {
  title: "",
  state: "CA",
  county: "",
  apn: "",
  acreage: "",
  asking_price_usd: "",
  latitude: "",
  longitude: "",
  description: "",
  source_url: "",
  address: "",
};

export default function IngestPage() {
  const [result, setResult] = useState<{ parcel_id?: string; score_id?: string } | null>(null);
  const [error, setError] = useState("");
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [urlBusy, setUrlBusy] = useState(false);
  const [pasteUrl, setPasteUrl] = useState("");
  const [step, setStep] = useState(0); // 0 = URL paste, 1-3 = manual confirm
  const [form, setForm] = useState<FormState>(EMPTY);

  function applyDraft(draft: Record<string, unknown>) {
    setForm((f) => ({
      ...f,
      title: String(draft.title || f.title || ""),
      state: String(draft.state || f.state || "CA").slice(0, 2).toUpperCase(),
      county: String(draft.county || f.county || ""),
      address: String(draft.address || f.address || ""),
      acreage: draft.acreage != null ? String(draft.acreage) : f.acreage,
      asking_price_usd:
        draft.asking_price_usd != null ? String(draft.asking_price_usd) : f.asking_price_usd,
      latitude: draft.latitude != null ? String(draft.latitude) : f.latitude,
      longitude: draft.longitude != null ? String(draft.longitude) : f.longitude,
      description: String(draft.description || f.description || ""),
      source_url: String(draft.source_url || f.source_url || pasteUrl),
      apn: String(draft.apn || f.apn || ""),
    }));
  }

  async function analyzeUrl() {
    setUrlBusy(true);
    setError("");
    setNote(null);
    setResult(null);
    try {
      const res = await landsignalApi.ingestFromUrl(pasteUrl.trim());
      if (res.draft) applyDraft(res.draft);
      if (res.note) setNote(res.note);
      if (res.error && !res.ok) setError(res.error);
      setStep(1);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not read that URL");
      setForm((f) => ({
        ...f,
        source_url: pasteUrl.trim(),
        title: f.title || "Listing from pasted URL",
      }));
      setNote(
        "Automatic extract failed — enter the details from the listing page, then run intelligence.",
      );
      setStep(1);
    } finally {
      setUrlBusy(false);
    }
  }

  async function submitManual() {
    setBusy(true);
    setError("");
    try {
      if (!form.title.trim()) throw new Error("Title is required");
      if (!form.state || form.state.length !== 2) throw new Error("State is required");
      const acres = Number(form.acreage);
      if (!Number.isFinite(acres) || acres <= 0) throw new Error("Acreage is required");
      const lat = Number(form.latitude);
      const lon = Number(form.longitude);
      if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
        throw new Error("Latitude and longitude are required (copy from the map on the listing)");
      }
      const body = {
        title: form.title.trim(),
        state: form.state.toUpperCase(),
        county: form.county || null,
        apn: form.apn || null,
        address: form.address || null,
        acreage: acres,
        asking_price_usd: form.asking_price_usd ? Number(form.asking_price_usd) : null,
        latitude: lat,
        longitude: lon,
        description: form.description || null,
        source_url: form.source_url || pasteUrl || null,
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
        <h1 className="display text-3xl font-semibold">Analyze a listing</h1>
        <p className="mt-1 text-sm text-[var(--muted)]">
          Paste a Land.com, Zillow, Crexi, or other listing URL you found. LandSignal builds an
          intelligence report from that one property — we do not bulk-import marketplace inventory.
        </p>
      </div>

      {step === 0 && (
        <section className="panel space-y-3 p-5">
          <label className="text-xs uppercase tracking-wide text-[var(--muted)]">
            Listing URL
            <input
              className="field mt-1"
              value={pasteUrl}
              onChange={(e) => setPasteUrl(e.target.value)}
              placeholder="https://www.land.com/property/…"
            />
          </label>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              className="btn btn-dark"
              disabled={urlBusy || !pasteUrl.trim()}
              onClick={() => void analyzeUrl()}
            >
              {urlBusy ? "Reading listing…" : "Extract & continue"}
            </button>
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => {
                setForm(EMPTY);
                setPasteUrl("");
                setNote("Enter the parcel manually — same intelligence engine.");
                setStep(1);
              }}
            >
              Enter manually instead
            </button>
          </div>
          {error && <div className="text-sm text-[var(--danger)]">{error}</div>}
          <p className="text-xs text-[var(--muted)]">
            Some sites hide details from bots. If extract is incomplete, fill the missing fields —
            Opportunity Score, Closest, and Future Scenario Engine still run on public data.
          </p>
        </section>
      )}

      {step > 0 && (
        <>
          <div className="flex flex-wrap gap-2 text-sm">
            {["Basics", "Location & price", "Review"].map((label, i) => (
              <button
                key={label}
                type="button"
                className={`rounded-full px-3 py-1.5 border ${
                  step === i + 1
                    ? "bg-[var(--brand)] text-white border-[var(--brand)]"
                    : "border-[var(--line)]"
                }`}
                onClick={() => setStep(i + 1)}
              >
                {i + 1}. {label}
              </button>
            ))}
            <button type="button" className="rounded-full border border-[var(--line)] px-3 py-1.5" onClick={() => setStep(0)}>
              ← URL
            </button>
          </div>

          {note ? <div className="panel p-4 text-sm text-[var(--muted)]">{note}</div> : null}

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
                County / city
                <input
                  className="field"
                  value={form.county}
                  onChange={(e) => setForm((f) => ({ ...f, county: e.target.value }))}
                />
              </label>
              <label className="text-xs uppercase tracking-wide text-[var(--muted)] md:col-span-2">
                Address (optional)
                <input
                  className="field"
                  value={form.address}
                  onChange={(e) => setForm((f) => ({ ...f, address: e.target.value }))}
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
                  ["apn", "APN / parcel ID (optional)"],
                  ["acreage", "Acreage"],
                  ["asking_price_usd", "Asking / bid price (blank if unpriced)"],
                  ["latitude", "Latitude"],
                  ["longitude", "Longitude"],
                  ["source_url", "Listing link"],
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
                    <dd className="font-medium break-all">{v || "—"}</dd>
                  </div>
                ))}
              </dl>
              <div className="flex flex-wrap gap-2">
                <button type="button" className="btn btn-ghost" onClick={() => setStep(2)}>
                  Back
                </button>
                <button type="button" className="btn btn-dark" onClick={() => void submitManual()} disabled={busy}>
                  {busy ? "Scoring…" : "Run Land Signal intelligence"}
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
        </>
      )}
    </div>
  );
}
