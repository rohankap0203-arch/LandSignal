"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { AcquireRail } from "@/components/acquire-rail";
import { LandLoader } from "@/components/land-loader";
import { ReturnVisual } from "@/components/return-visual";
import { ScoreBar } from "@/components/score-bar";
import { SignalBadge } from "@/components/signal-badge";
import { SignalCockpit } from "@/components/signal-cockpit";
import { landsignalApi, type ActionLink } from "@/lib/api";

const ParcelMap = dynamic(() => import("@/components/parcel-map").then((m) => m.ParcelMap), {
  ssr: false,
});

type AnyRec = Record<string, unknown>;

function LinkButton({ link }: { link: ActionLink }) {
  // Never show error codes / unavailable — every URL we render is clickable
  if (!link.url) return null;
  return (
    <a href={link.url} target="_blank" rel="noreferrer" className="btn btn-ghost">
      {link.label}
    </a>
  );
}

export default function ParcelIntelligencePage() {
  const params = useParams<{ id: string }>();
  const [data, setData] = useState<AnyRec | null>(null);
  const [memo, setMemo] = useState<string | null>(null);
  const [verdict, setVerdict] = useState<string | null>(null);
  const [memoLoading, setMemoLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ddOpen, setDdOpen] = useState<Record<string, boolean>>({});
  const [watched, setWatched] = useState(false);
  const [watchMsg, setWatchMsg] = useState("");
  const [openRating, setOpenRating] = useState<string | null>(null);

  useEffect(() => {
    setData(null);
    setError(null);
    landsignalApi
      .parcel(params.id)
      .then((d) => {
        setData(d);
        setWatched(Boolean(d.watched));
      })
      .catch((e: Error) => setError(e.message));
  }, [params.id]);

  if (error) return <div className="panel p-5 text-[var(--danger)]">{error}</div>;
  if (!data) {
    return (
      <LandLoader
        label="Building land intelligence…"
        detail="Soils, flood, wetlands, settle math, and return screens for this exact pin."
      />
    );
  }

  const parcel = data.parcel as AnyRec;
  const listing = data.listing as AnyRec | null;
  const score = data.score as AnyRec | null;
  const links = (data.links as ActionLink[]) || [];
  const price = data.price as AnyRec;
  const ratings = (data.rating_breakdown as AnyRec[]) || [];
  const land = (data.land_readouts as Record<string, AnyRec>) || {};
  const brief = (data.brief as AnyRec) || {};
  const cockpit = (data.cockpit as AnyRec) || {};
  const sourcing = (data.sourcing as AnyRec) || ((cockpit.source as AnyRec) || {});
  const whyOpp = (brief.why_opportunity as AnyRec[]) || [];
  const whyStill = (brief.why_still_available as AnyRec[]) || [];
  const scenarios = (brief.scenario_cards as AnyRec[]) || (data.scenarios_human as AnyRec[]) || [];
  const dd = (brief.dd_focus as AnyRec[]) || (data.due_diligence_guided as AnyRec[]) || [];
  const story = (brief.score_story as Record<string, string>) || {};
  const returnCase = (brief.return_case as AnyRec) || {};

  const identity = [
    parcel.apn ? String(parcel.apn) : null,
    parcel.county ? `${parcel.county}, ${parcel.state}` : String(parcel.state || ""),
    parcel.acreage != null ? `${Number(parcel.acreage).toFixed(2)} ac` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  const sellerLink =
    links.find((l) => l.kind === "primary") ||
    (sourcing.website
      ? { label: "Open posting", url: String(sourcing.website), kind: "primary", available: true }
      : null);
  const phone =
    (sourcing.phone ? String(sourcing.phone) : null) ||
    links.find((l) => l.kind === "contact" && String(l.url).startsWith("tel:"))?.label ||
    null;
  const findLink = links.find((l) => l.kind === "lookup") || null;

  async function toggleWatch() {
    try {
      if (watched) {
        await landsignalApi.unwatch(params.id);
        setWatched(false);
        setWatchMsg("Removed from watchlist.");
      } else {
        const res = await landsignalApi.watch(params.id);
        setWatched(true);
        setWatchMsg(String(res.note || "Added to watchlist."));
      }
    } catch (e) {
      setWatchMsg(e instanceof Error ? e.message : "Watchlist update failed");
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link href="/" className="text-sm text-[var(--muted)] hover:text-[var(--brand)]">
          ← Back to results
        </Link>
        <div className="flex flex-wrap items-center gap-2">
          <Link href="/watchlist" className="text-sm text-[var(--muted)] hover:text-[var(--brand)]">
            Open watchlist
          </Link>
          <button type="button" className={`btn ${watched ? "btn-dark" : "btn-primary"}`} onClick={toggleWatch}>
            {watched ? "Watching ✓" : "Add to watchlist"}
          </button>
        </div>
      </div>
      {(watchMsg || brief.watch_hint) && (
        <div className="panel px-4 py-3 text-sm text-[var(--muted)]">{watchMsg || String(brief.watch_hint)}</div>
      )}

      <section className="panel overflow-hidden">
        <div className="grid gap-0 lg:grid-cols-[1.05fr_0.95fr]">
          <div className="p-6">
            <div className="flex flex-wrap items-center gap-2">
              {score && <SignalBadge signal={score.signal as string} />}
              <span className="rounded-full bg-[var(--bg-soft)] px-3 py-1 text-xs font-semibold">
                {String(sourcing.source_name || "Public source")}
              </span>
            </div>
            <h1 className="display mt-3 text-3xl font-semibold leading-tight break-words">
              {(listing?.title as string) || (parcel.apn as string)}
            </h1>
            <p className="mt-2 text-[var(--muted)] break-words">{identity}</p>

            <div className="mt-5 grid gap-4">
              <ScoreBar label="LandSignal" value={Number(score?.opportunity || 0)} hint={story.landsignal} />
              <ScoreBar label="Risk" value={Number(score?.risk || 0)} invert hint={story.risk} />
              <ScoreBar
                label="Confidence"
                value={Number(score?.confidence || 0)}
                hint={story.confidence}
              />
            </div>

            <div className="mt-5 grid grid-cols-2 gap-3">
              <Stat label={String(price?.label || "Price")} value={String(price?.display || "No public ask")} />
              <Stat label="Deal readiness" value={`${Number(score?.deal_readiness || 0).toFixed(0)}/100`} />
            </div>

            {returnCase.headline ? (
              <div className="return-case mt-5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--muted)]">
                    Acquisition return case
                  </div>
                  <span className={`conviction-pill ${String(returnCase.conviction || "watch").toLowerCase()}`}>
                    {String(returnCase.conviction || "WATCH")}
                  </span>
                </div>
                <div className="mt-1 font-semibold leading-snug break-words">{String(returnCase.headline)}</div>
                <ul className="mt-2 space-y-1 text-sm text-[var(--muted)]">
                  {((returnCase.bullets as string[]) || []).slice(0, 4).map((b) => (
                    <li key={b}>• {b}</li>
                  ))}
                </ul>
              </div>
            ) : null}

            <div className="source-card mt-5">
              <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--muted)]">Contact this land</div>
              <div className="font-semibold break-words">{String(sourcing.office || "County office")}</div>
              <AcquireRail
                className="mt-3"
                postingUrl={sellerLink?.url || String(sourcing.website || "")}
                phone={phone}
                office={sourcing.office ? String(sourcing.office) : null}
                findUrl={findLink?.url}
                findLabel={findLink?.label}
              />
              {sourcing.how_to_buy ? (
                <p className="mt-2 text-xs leading-relaxed text-[var(--muted)]">{String(sourcing.how_to_buy)}</p>
              ) : null}
            </div>

            <div className="mt-4 flex flex-wrap gap-2">
              {links
                .filter(
                  (l) =>
                    l.url &&
                    l.url !== sellerLink?.url &&
                    l.url !== findLink?.url &&
                    !String(l.url).startsWith("tel:") &&
                    l.kind !== "map" &&
                    l.kind !== "primary" &&
                    l.kind !== "contact",
                )
                .map((link, i) => (
                  <LinkButton key={`${link.url}-${i}`} link={link} />
                ))}
              <button
                type="button"
                className="btn btn-ghost"
                disabled={memoLoading}
                onClick={() => {
                  setMemoLoading(true);
                  landsignalApi
                    .memo(params.id)
                    .then((m) => {
                      setMemo(m.markdown);
                      setVerdict(m.verdict);
                    })
                    .finally(() => setMemoLoading(false));
                }}
              >
                {memoLoading ? "Writing memo…" : "Generate investment memo"}
              </button>
            </div>
          </div>

          <div className="flex flex-col border-t border-[var(--line)] lg:border-l lg:border-t-0">
            <ParcelMap
              latitude={parcel.latitude as number}
              longitude={parcel.longitude as number}
              polygon={parcel.polygon as number[][][]}
              title={listing?.title as string}
              height={280}
            />
            <div className="border-t border-[var(--line)] p-4">
              <SignalCockpit cockpit={cockpit} />
            </div>
          </div>
        </div>
      </section>

      {memoLoading && (
        <LandLoader compact label="Composing investment memo…" detail="Weighing this parcel’s score, constraints, and gaps." />
      )}

      <section className="panel p-5">
        <ReturnVisual
          cases={scenarios as never[]}
          identity={identity}
          entryLabel={
            returnCase.entry_usd != null
              ? `$${Number(returnCase.entry_usd).toLocaleString(undefined, { maximumFractionDigits: 0 })}`
              : undefined
          }
          markLabel={
            returnCase.mark_usd != null
              ? `$${Number(returnCase.mark_usd).toLocaleString(undefined, { maximumFractionDigits: 0 })}`
              : undefined
          }
        />
      </section>

      <section className="grid gap-4 md:grid-cols-2">
        <InsightList title={`Why ${parcel.apn || "this parcel"}`} items={whyOpp} />
        <InsightList title="Why it may still be available" items={whyStill} />
      </section>

      <section className="panel p-5">
        <h2 className="display text-xl font-semibold">Rating breakdown · {identity}</h2>
        <p className="mt-1 text-sm text-[var(--muted)]">
          Each score below explains the exact inputs for this parcel — tap for drivers.
        </p>
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          {ratings.map((r) => {
            const scoreN = Number(r.score || 0);
            const key = String(r.key);
            const open = openRating === key;
            return (
              <button
                key={key}
                type="button"
                className="rounded-2xl bg-[var(--bg-soft)] p-4 text-left transition hover:ring-1 hover:ring-[var(--brand-soft)]"
                onClick={() => setOpenRating(open ? null : key)}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="font-semibold">{String(r.label)}</div>
                  <div className="text-sm font-semibold whitespace-nowrap">
                    {String(r.score_display || `${scoreN.toFixed(0)}/100`)}
                  </div>
                </div>
                <div className="mt-2 h-2 overflow-hidden rounded-full bg-[var(--bg-elevated)]">
                  <div
                    className="h-full rounded-full transition-all"
                    style={{
                      width: `${Math.max(4, Math.min(100, scoreN))}%`,
                      background: `hsl(${scoreN * 1.2} 65% 42%)`,
                    }}
                  />
                </div>
                <p className="mt-2 text-sm leading-relaxed text-[var(--ink)]">
                  {String(r.why_this_number || r.plain_english || r.simple || "")}
                </p>
                {open && (
                  <div className="mt-2 space-y-1 text-sm text-[var(--muted)]">
                    <div className="text-xs">{String(r.weight_display || "")}</div>
                    <ul className="space-y-1">
                      {((r.drivers as string[]) || (r.evidence as string[]) || []).map((e) => (
                        <li key={e}>• {e}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </button>
            );
          })}
        </div>
      </section>

      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {(["soil", "flood", "wetlands", "transmission"] as const).map((key) => {
          const card = land[key] || {};
          const addKey =
            key === "soil"
              ? "soil_addendum"
              : key === "flood"
                ? "flood_addendum"
                : key === "wetlands"
                  ? "wetlands_addendum"
                  : "transmission_addendum";
          // Prefer addenda that mention this APN; skip generic duplicates of plain_english
          const addenda = ((brief[addKey] as string[]) || []).filter(
            (a) => a && !String(card.plain_english || "").includes(a.slice(0, 24)),
          );
          return (
            <div key={key} className="panel p-4 text-left">
              <div className="flex items-center justify-between gap-2">
                <h3 className="font-semibold">{String(card.title || key)}</h3>
                <span className="text-[10px] uppercase tracking-wide text-[var(--muted)]">
                  {String(card.level || card.knowledge_state || "")}
                </span>
              </div>
              <p className="mt-2 text-sm leading-relaxed">{String(card.plain_english || "No reading for this pin yet.")}</p>
              <ul className="mt-2 space-y-1 text-sm text-[var(--muted)]">
                {((card.bullets as string[]) || []).slice(0, 3).map((b) => (
                  <li key={b}>• {b}</li>
                ))}
                {addenda.slice(0, 2).map((a) => (
                  <li key={a}>• {a}</li>
                ))}
              </ul>
            </div>
          );
        })}
      </section>

      <section className="panel p-5">
        <h2 className="display text-xl font-semibold">
          Diligence for {String(parcel.apn || "this parcel")} · readiness{" "}
          {Number(score?.deal_readiness || 0).toFixed(0)}/100
        </h2>
        <div className="mt-4 grid gap-2">
          {dd.map((item) => {
            const label = String(item.label);
            const open = ddOpen[label];
            return (
              <button
                key={label}
                type="button"
                className="rounded-2xl border border-[var(--line)] bg-[var(--bg-soft)] p-3 text-left"
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
                    <p>{String(item.parcel_note || item.why_it_matters)}</p>
                    <p>
                      <strong className="text-[var(--ink)]">Start:</strong> {String(item.how_to_start)}
                    </p>
                  </div>
                )}
              </button>
            );
          })}
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

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl bg-[var(--bg-soft)] p-3">
      <div className="text-[10px] uppercase tracking-wide text-[var(--muted)]">{label}</div>
      <div className="mt-1 font-semibold break-words">{value}</div>
    </div>
  );
}

function InsightList({ title, items }: { title: string; items: AnyRec[] }) {
  const [open, setOpen] = useState(0);
  return (
    <div className="panel p-5">
      <h2 className="display text-xl font-semibold">{title}</h2>
      <div className="mt-3 space-y-2">
        {items.map((item, i) => (
          <button
            key={`${String(item.headline || item)}-${i}`}
            type="button"
            className="w-full rounded-2xl bg-[var(--bg-soft)] p-3 text-left"
            onClick={() => setOpen(open === i ? -1 : i)}
          >
            <div className="font-semibold">{String(item.headline || item)}</div>
            {open === i && item.detail ? (
              <p className="mt-2 text-sm leading-relaxed text-[var(--muted)]">{String(item.detail)}</p>
            ) : null}
          </button>
        ))}
        {!items.length && <p className="text-sm text-[var(--muted)]">No parcel-specific narrative yet.</p>}
      </div>
    </div>
  );
}
