"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { SignalBadge } from "@/components/signal-badge";
import { landsignalApi, type ActionLink } from "@/lib/api";

const ParcelMap = dynamic(() => import("@/components/parcel-map").then((m) => m.ParcelMap), {
  ssr: false,
});

type AnyRec = Record<string, unknown>;

function LinkButton({ link, dark }: { link: ActionLink; dark?: boolean }) {
  const available = link.available !== false;
  if (!available) {
    return (
      <span className="btn btn-ghost opacity-45 cursor-not-allowed" title="Document not currently available">
        {link.label} (unavailable)
      </span>
    );
  }
  return (
    <a href={link.url} target="_blank" rel="noreferrer" className={`btn ${dark ? "btn-dark" : "btn-ghost"}`}>
      {link.label}
    </a>
  );
}

export default function ParcelIntelligencePage() {
  const params = useParams<{ id: string }>();
  const [data, setData] = useState<AnyRec | null>(null);
  const [memo, setMemo] = useState<string | null>(null);
  const [verdict, setVerdict] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ddOpen, setDdOpen] = useState<Record<string, boolean>>({});

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
  const links = (data.links as ActionLink[]) || [];
  const price = data.price as AnyRec;
  const ratings = (data.rating_breakdown as AnyRec[]) || [];
  const dd = (data.due_diligence_guided as AnyRec[]) || [];
  const land = (data.land_readouts as Record<string, AnyRec>) || {};
  const scenarios = (data.scenarios_human as AnyRec[]) || [];
  const explained = (data.score_explained as Record<string, string>) || {};
  const narratives = (enrichment?.narratives as AnyRec) || {};
  const whyUnsold = (narratives.why_unsold as AnyRec) || {};

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
              <Stat
                label="LandSignal"
                value={`${Number(score?.opportunity || 0).toFixed(0)}/100`}
                hint={explained.landsignal}
              />
              <Stat label="Risk" value={`${Number(score?.risk || 0).toFixed(0)}/100`} hint={explained.risk} />
              <Stat
                label="Confidence"
                value={`${Number(score?.confidence || 0).toFixed(0)}/100`}
                hint={explained.confidence}
              />
            </div>

            <div className="mt-5 flex flex-wrap gap-2">
              {links.map((link, i) => (
                <LinkButton key={`${link.url}-${i}`} link={link} dark={i === 0 && link.available !== false} />
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
            {(
              ((whyUnsold.most_likely as AnyRec)?.evidence as string[]) ||
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
          Each bar is a piece of the LandSignal score. Read the plain-English line first, then the evidence.
        </p>
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          {ratings.map((r) => {
            const scoreN = Number(r.score || 0);
            return (
              <div key={String(r.key)} className="rounded-2xl bg-[var(--bg-soft)] p-4">
                <div className="flex items-center justify-between gap-2">
                  <div className="font-semibold">{String(r.label)}</div>
                  <div className="text-sm font-semibold">{String(r.score_display || `${scoreN.toFixed(0)}/100`)}</div>
                </div>
                <p className="mt-1 text-sm text-[var(--muted)]">{String(r.simple || "")}</p>
                <div className="mt-2 h-2 overflow-hidden rounded-full bg-[var(--bg-elevated)]">
                  <div
                    className="h-full rounded-full bg-[var(--brand-soft)] transition-all"
                    style={{ width: `${Math.max(4, Math.min(100, scoreN))}%` }}
                  />
                </div>
                <div className="mt-2 text-xs text-[var(--muted)]">
                  {String(r.weight_display || `${r.weight_pct}% of score`)} · {String(r.knowledge_state)}
                </div>
                <p className="mt-2 text-sm font-medium">{String(r.plain_english || "")}</p>
                <ul className="mt-2 space-y-1 text-sm text-[var(--muted)]">
                  {((r.evidence as string[]) || []).map((e) => (
                    <li key={e}>• {e}</li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>
      </section>

      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {(["soil", "flood", "wetlands", "transmission"] as const).map((key) => (
          <HumanCard key={key} data={land[key]} />
        ))}
      </section>

      {!!scenarios.length && (
        <section className="panel p-5">
          <h2 className="display text-xl font-semibold">Hold-period farmland scenarios</h2>
          <p className="mt-1 text-sm text-[var(--muted)]">
            Simple what-if screens for farming income. These are estimates for sorting deals — not a promise.
          </p>
          <div className="mt-4 grid gap-3 md:grid-cols-3">
            {scenarios.map((s) => (
              <div key={String(s.case_type)} className="rounded-2xl bg-[var(--bg-soft)] p-4">
                <div className="font-semibold">{String(s.case_label || s.case_type)}</div>
                <p className="mt-2 text-sm text-[var(--muted)]">{String(s.plain_english || "")}</p>
                <dl className="mt-3 grid gap-2 text-sm">
                  <div className="flex justify-between gap-2">
                    <dt className="text-[var(--muted)]">Yearly income (NOI)</dt>
                    <dd className="font-semibold">{String(s.noi_display)}</dd>
                  </div>
                  <div className="flex justify-between gap-2">
                    <dt className="text-[var(--muted)]">Return (IRR)</dt>
                    <dd className="font-semibold">{String(s.irr_display)}</dd>
                  </div>
                  <div className="flex justify-between gap-2">
                    <dt className="text-[var(--muted)]">Value today (NPV)</dt>
                    <dd className="font-semibold">{String(s.npv_display)}</dd>
                  </div>
                  <div className="flex justify-between gap-2">
                    <dt className="text-[var(--muted)]">Breakeven land price</dt>
                    <dd className="font-semibold">{String(s.breakeven_display)}</dd>
                  </div>
                </dl>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="panel p-5">
        <h2 className="display text-xl font-semibold">
          Manual due diligence · readiness {Number(score?.deal_readiness || 0).toFixed(0)}/100
        </h2>
        <p className="mt-1 text-sm text-[var(--muted)]">
          {explained.deal_readiness ||
            "A checklist of real next steps. Tap a row to see why it matters and how to start."}
        </p>
        <div className="mt-4 grid gap-2">
          {dd.map((item) => {
            const label = String(item.label);
            const open = ddOpen[label];
            return (
              <button
                key={label}
                type="button"
                className="rounded-2xl border border-[var(--line)] bg-[var(--bg-soft)] p-3 text-left transition hover:border-[var(--brand-soft)]"
                onClick={() => setDdOpen((s) => ({ ...s, [label]: !s[label] }))}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="font-semibold">
                    {item.completed ? "☑" : "☐"} {label}
                  </div>
                  <span className="rounded-full bg-[var(--bg-elevated)] px-2 py-0.5 text-xs font-semibold">
                    {String(item.priority || "Soon")}
                  </span>
                </div>
                {open && (
                  <div className="mt-2 space-y-1 text-sm text-[var(--muted)]">
                    <p>
                      <strong className="text-[var(--ink)]">Why it matters:</strong>{" "}
                      {String(item.why_it_matters)}
                    </p>
                    <p>
                      <strong className="text-[var(--ink)]">How to start:</strong> {String(item.how_to_start)}
                    </p>
                  </div>
                )}
              </button>
            );
          })}
          {!dd.length && (
            <p className="text-sm text-[var(--muted)]">Due diligence checklist will appear after analysis.</p>
          )}
        </div>
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

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-2xl bg-[var(--bg-soft)] p-3" title={hint}>
      <div className="text-[10px] uppercase tracking-wide text-[var(--muted)]">{label}</div>
      <div className="mt-1 font-semibold overflow-wrap-anywhere">{value}</div>
    </div>
  );
}

function HumanCard({ data }: { data?: AnyRec }) {
  if (!data) {
    return (
      <div className="panel p-4">
        <h3 className="font-semibold">Land screen</h3>
        <p className="mt-2 text-sm text-[var(--muted)]">No reading yet — confidence reduced.</p>
      </div>
    );
  }
  return (
    <div className="panel p-4">
      <div className="flex items-center justify-between gap-2">
        <h3 className="font-semibold">{String(data.title)}</h3>
        <span className="text-[10px] uppercase tracking-wide text-[var(--muted)]">
          {String(data.level || data.knowledge_state || "")}
        </span>
      </div>
      <p className="mt-2 text-sm leading-relaxed">{String(data.plain_english)}</p>
      <ul className="mt-2 space-y-1 text-sm text-[var(--muted)]">
        {((data.bullets as string[]) || []).map((b) => (
          <li key={b}>• {b}</li>
        ))}
      </ul>
      <div className="mt-2 text-[11px] text-[var(--muted)]">
        Source: {String(data.source || "n/a")}
        {data.confidence != null ? ` · evidence strength ${String(data.confidence)}` : ""}
      </div>
    </div>
  );
}
