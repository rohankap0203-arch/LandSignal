"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { SignalBadge } from "@/components/signal-badge";
import { landsignalApi } from "@/lib/api";

const ParcelMap = dynamic(() => import("@/components/parcel-map").then((m) => m.ParcelMap), {
  ssr: false,
});

type AnyRec = Record<string, unknown>;

export default function ParcelIntelligencePage() {
  const params = useParams<{ id: string }>();
  const [data, setData] = useState<AnyRec | null>(null);
  const [memo, setMemo] = useState<string | null>(null);
  const [verdict, setVerdict] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    landsignalApi
      .parcel(params.id)
      .then(setData)
      .catch((e: Error) => setError(e.message));
  }, [params.id]);

  if (error) return <div className="panel p-5 text-[var(--danger)]">{error}</div>;
  if (!data) return <div className="text-[var(--muted)]">Loading property intelligence…</div>;

  const parcel = data.parcel as AnyRec;
  const listing = data.listing as AnyRec | null;
  const score = data.score as AnyRec | null;
  const enrichment = data.enrichment as AnyRec | null;
  const links = (data.links as Array<{ label: string; url: string }>) || [];
  const price = data.price as AnyRec;
  const ratings = (data.rating_breakdown as AnyRec[]) || [];
  const dd = (data.due_diligence as AnyRec[]) || [];
  const narratives = (enrichment?.narratives as AnyRec) || {};
  const whyUnsold = (narratives.why_unsold as AnyRec) || {};
  const scenarios = (enrichment?.scenarios as AnyRec[]) || [];

  return (
    <div className="space-y-5">
      <Link href="/" className="text-sm text-[var(--muted)] hover:text-[var(--brand)]">
        ← Back to results
      </Link>

      <section className="panel overflow-hidden">
        <div className="grid gap-0 lg:grid-cols-[1.1fr_0.9fr]">
          <div className="p-6">
            <div className="flex flex-wrap items-center gap-2">
              {score && <SignalBadge signal={score.signal as string} />}
              <span className="rounded-full bg-[var(--bg-soft)] px-3 py-1 text-xs font-semibold">
                LIVE PUBLIC SOURCE
              </span>
            </div>
            <h1 className="display mt-3 text-3xl font-semibold leading-tight">
              {(listing?.title as string) || (parcel.apn as string)}
            </h1>
            <p className="mt-2 text-[var(--muted)]">
              {parcel.county as string}, {parcel.state as string}
              {parcel.acreage != null ? ` · ${Number(parcel.acreage).toFixed(2)} acres` : ""}
              {parcel.apn ? ` · ${String(parcel.apn)}` : ""}
            </p>
            <p className="mt-4 max-w-2xl text-[15px] leading-relaxed text-[var(--ink)]">
              {String(listing?.description || "No description published by source.")}
            </p>

            <div className="mt-5 grid grid-cols-2 gap-3 md:grid-cols-4">
              <Stat label={String(price?.label || "Price")} value={String(price?.display || "Contact source")} />
              <Stat label="LandSignal" value={`${Number(score?.opportunity || 0).toFixed(0)}/100`} />
              <Stat label="Risk" value={`${Number(score?.risk || 0).toFixed(0)}/100`} />
              <Stat label="Confidence" value={`${Number(score?.confidence || 0).toFixed(0)}/100`} />
            </div>

            <div className="mt-5 flex flex-wrap gap-2">
              {links.map((link, i) => (
                <a
                  key={link.url}
                  href={link.url}
                  target="_blank"
                  rel="noreferrer"
                  className={`btn ${i === 0 ? "btn-dark" : "btn-ghost"}`}
                >
                  {link.label}
                </a>
              ))}
              <button
                type="button"
                className="btn btn-ghost"
                onClick={() =>
                  landsignalApi.memo(params.id).then((m) => {
                    setMemo(m.markdown);
                    setVerdict(m.verdict);
                  })
                }
              >
                Generate investment memo
              </button>
            </div>
          </div>
          <div className="min-h-[280px] border-t border-[var(--line)] lg:border-l lg:border-t-0">
            <ParcelMap
              latitude={parcel.latitude as number}
              longitude={parcel.longitude as number}
              polygon={parcel.polygon as number[][][]}
              title={listing?.title as string}
              height={360}
            />
          </div>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-2">
        <div className="panel p-5">
          <h2 className="display text-xl font-semibold">Why this opportunity</h2>
          <ul className="reasons mt-3">
            {((score?.why_interesting as string[]) || ["See score components below"]).map((x) => (
              <li key={x}>{x}</li>
            ))}
          </ul>
        </div>
        <div className="panel p-5">
          <h2 className="display text-xl font-semibold">Why it may still be available</h2>
          <p className="mt-2 text-sm font-semibold">
            {String((whyUnsold.most_likely as AnyRec)?.reason || "See evidence below")}
          </p>
          <ul className="reasons">
            {(((whyUnsold.most_likely as AnyRec)?.evidence as string[]) ||
              (score?.why_still_available as string[]) ||
              []
            ).map((x) => (
              <li key={x}>{x}</li>
            ))}
          </ul>
        </div>
      </section>

      <section className="panel p-5">
        <h2 className="display text-xl font-semibold">Backed rating breakdown</h2>
        <p className="mt-1 text-sm text-[var(--muted)]">
          Each category contributes to LandSignal with explicit evidence — missing data lowers confidence, not
          invents quality.
        </p>
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          {ratings.map((r) => (
            <div key={String(r.key)} className="rounded-2xl bg-[var(--bg-soft)] p-4">
              <div className="flex items-center justify-between gap-2">
                <div className="font-semibold">{String(r.label)}</div>
                <div className="text-sm font-semibold">
                  {Number(r.score).toFixed(0)} · wt {Number(r.weight_pct)}%
                </div>
              </div>
              <div className="mt-1 text-xs uppercase tracking-wide text-[var(--muted)]">
                {String(r.knowledge_state)}
              </div>
              <ul className="mt-2 space-y-1 text-sm text-[var(--muted)]">
                {((r.evidence as string[]) || []).map((e) => (
                  <li key={e}>• {e}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>

      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <EnrichCard title="Soils" prov={enrichment?.soil as AnyRec} />
        <EnrichCard title="Flood" prov={enrichment?.flood as AnyRec} />
        <EnrichCard title="Wetlands" prov={enrichment?.wetlands as AnyRec} />
        <EnrichCard title="Transmission" prov={enrichment?.infrastructure as AnyRec} />
      </section>

      {!!scenarios.length && (
        <section className="panel p-5">
          <h2 className="display text-xl font-semibold">Hold-period farmland scenarios</h2>
          <p className="mt-1 text-sm text-[var(--muted)]">Estimated — for screening, not a commitment.</p>
          <div className="mt-4 overflow-x-auto">
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead>
                <tr className="text-[var(--muted)]">
                  <th className="py-2">Case</th>
                  <th>NOI</th>
                  <th>IRR</th>
                  <th>NPV</th>
                  <th>Breakeven land</th>
                </tr>
              </thead>
              <tbody>
                {scenarios.map((s) => (
                  <tr key={String(s.case_type)} className="border-t border-[var(--line)]">
                    <td className="py-2 font-semibold">{String(s.case_type)}</td>
                    <td>${Number(s.noi || 0).toLocaleString()}</td>
                    <td>{s.irr != null ? `${(Number(s.irr) * 100).toFixed(1)}%` : "n/a"}</td>
                    <td>${Number(s.npv || 0).toLocaleString()}</td>
                    <td>
                      {s.breakeven_land_value != null
                        ? `$${Number(s.breakeven_land_value).toLocaleString()}`
                        : "n/a"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section className="panel p-5">
        <h2 className="display text-xl font-semibold">
          Manual due diligence · readiness {Number(score?.deal_readiness || 0).toFixed(0)}/100
        </h2>
        <ul className="mt-3 columns-1 gap-3 text-sm md:columns-2">
          {dd.map((item) => (
            <li key={String(item.label)} className="mb-2">
              ☐ {String(item.label)}
            </li>
          ))}
        </ul>
      </section>

      {memo && (
        <section className="panel p-5">
          <div className="flex items-center justify-between gap-3">
            <h2 className="display text-xl font-semibold">Investment memo</h2>
            <SignalBadge signal={verdict || "WATCH"} />
          </div>
          <pre className="mt-3 whitespace-pre-wrap text-sm leading-relaxed">{memo}</pre>
        </section>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl bg-[var(--bg-soft)] p-3">
      <div className="text-[10px] uppercase tracking-wide text-[var(--muted)]">{label}</div>
      <div className="mt-1 font-semibold overflow-wrap-anywhere">{value}</div>
    </div>
  );
}

function EnrichCard({ title, prov }: { title: string; prov?: AnyRec }) {
  const state = String(prov?.knowledge_state || "UNKNOWN");
  const payload = prov?.normalized || prov?.value;
  return (
    <div className="panel p-4">
      <div className="flex items-center justify-between gap-2">
        <h3 className="font-semibold">{title}</h3>
        <span className="text-[10px] uppercase tracking-wide text-[var(--muted)]">{state}</span>
      </div>
      <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap break-words text-xs text-[var(--muted)]">
        {payload ? JSON.stringify(payload, null, 2) : "No reading from source yet — confidence reduced."}
      </pre>
      <div className="mt-2 text-[11px] text-[var(--muted)]">
        Source: {String(prov?.source || "n/a")}
        {prov?.confidence != null ? ` · confidence ${String(prov.confidence)}` : ""}
      </div>
    </div>
  );
}
