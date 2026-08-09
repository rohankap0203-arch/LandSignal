"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { AcquireRail } from "@/components/acquire-rail";
import { LandLoader } from "@/components/land-loader";
import { PriceTrajectory } from "@/components/price-trajectory";
import { ReturnVisual } from "@/components/return-visual";
import { ScoreBar } from "@/components/score-bar";
import { SignalBadge } from "@/components/signal-badge";
import { SignalCockpit } from "@/components/signal-cockpit";
import { landsignalApi, type ActionLink } from "@/lib/api";

const ParcelMap = dynamic(() => import("@/components/parcel-map").then((m) => m.ParcelMap), {
  ssr: false,
});

type AnyRec = Record<string, unknown>;

function firstSentence(text: unknown, max = 140): string {
  const s = String(text || "").trim();
  if (!s) return "";
  const cut = s.split(/(?<=[.!?])\s+/)[0] || s;
  return cut.length > max ? cut.slice(0, max - 1).trimEnd() + "…" : cut;
}


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
        detail="Soils, flood, wetlands, likely buy price, and yearly-return screens for this exact pin."
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

  const place = parcel.county
    ? `${parcel.county}, ${parcel.state}`
    : String(parcel.state || "Location on file");
  const identity = [
    place,
    parcel.acreage != null ? `${Number(parcel.acreage).toFixed(2)} acres` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  const pageTitle = (() => {
    const raw = String((listing?.title as string) || "");
    const cleaned = raw
      .replace(/\bAPN\s*[:#]?\s*[\w./-]+/gi, "")
      .replace(/\b\d{7,}\b/g, "")
      .replace(/\s*[·|]\s*/g, " · ")
      .replace(/(?:\s*·\s*)+/g, " · ")
      .replace(/\s{2,}/g, " ")
      .trim()
      .replace(/^·|·$/g, "")
      .trim();
    if (cleaned && !/^\d[\d.\-]*$/.test(cleaned)) return cleaned;
    const acres =
      parcel.acreage != null ? `${Number(parcel.acreage).toFixed(1)}-acre ` : "";
    return `${acres}property in ${place}`.replace(/^./, (c) => c.toUpperCase());
  })();

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
        <Link href="/watchlist" className="text-sm text-[var(--muted)] hover:text-[var(--brand)]">
          Open watchlist
        </Link>
      </div>

      <section className="panel overflow-hidden">
        <div className="grid gap-0 lg:grid-cols-[1.05fr_0.95fr]">
          <div className="p-6">
            <div className="intel-topbar">
              <div className="flex flex-wrap items-center gap-2 min-w-0">
                {score && <SignalBadge signal={score.signal as string} />}
                <span className="rounded-full bg-[var(--bg-soft)] px-3 py-1 text-xs font-semibold">
                  {String(sourcing.source_name || "Public source")}
                </span>
              </div>
              <button
                type="button"
                className={`watch-eye ${watched ? "on" : ""}`}
                onClick={toggleWatch}
                title={watched ? "Remove from watchlist" : "Add to watchlist"}
                aria-label={watched ? "Remove from watchlist" : "Add to watchlist"}
                aria-pressed={watched}
              >
                <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden>
                  {watched ? (
                    <>
                      <path
                        fill="currentColor"
                        d="M12 5c-7 0-10 7-10 7s3 7 10 7 10-7 10-7-3-7-10-7zm0 11a4 4 0 1 1 0-8 4 4 0 0 1 0 8z"
                      />
                      <circle fill="var(--bg-elevated)" cx="12" cy="12" r="2.2" />
                    </>
                  ) : (
                    <path
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.7"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"
                    />
                  )}
                  {!watched && <circle fill="currentColor" cx="12" cy="12" r="2.5" />}
                </svg>
                <span>{watched ? "Added" : "Add"}</span>
              </button>
            </div>
            <h1 className="display mt-3 text-3xl font-semibold leading-tight break-words">
              {pageTitle}
            </h1>
            <p className="mt-2 text-[var(--muted)] break-words">{identity}</p>
            {parcel.apn ? (
              <p className="mt-1 text-xs text-[var(--muted)]">
                County parcel ID (for assessor lookup only): {String(parcel.apn)}
              </p>
            ) : null}
            {watchMsg ? <p className="mt-2 text-xs text-[var(--muted)]">{watchMsg}</p> : null}

            <div className="mt-5 grid gap-4">
              <ScoreBar
                label="Opportunity score"
                value={Number(score?.opportunity || 0)}
                hint={firstSentence(story.landsignal)}
              />
              <ScoreBar label="Risk" value={Number(score?.risk || 0)} invert hint={firstSentence(story.risk)} />
              <ScoreBar
                label="How complete the file is"
                value={Number(score?.confidence || 0)}
                hint={firstSentence(story.confidence)}
              />
            </div>

            <div className="mt-5 grid grid-cols-2 gap-3">
              <Stat label={String(price?.label || "Price")} value={String(price?.display || "No public price yet")} />
              <Stat
                label="Ready to pursue? (0–100)"
                value={`${Number(score?.deal_readiness || 0).toFixed(0)}/100`}
              />
            </div>

            {price?.estimate_source ? (
              <div className="estimate-source mt-4">
                <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--muted)]">
                  {String((price.estimate_source as AnyRec).headline || "Where our estimate comes from")}
                </div>
                <p className="mt-1 text-sm leading-relaxed">
                  {String((price.estimate_source as AnyRec).summary || "")}
                </p>
                <ul className="mt-2 space-y-1 text-sm text-[var(--muted)]">
                  {(((price.estimate_source as AnyRec).bullets as string[]) || []).slice(0, 3).map((b) => (
                    <li key={b}>• {b}</li>
                  ))}
                </ul>
              </div>
            ) : null}

            {returnCase.headline ? (
              <div className="return-case mt-5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--muted)]">
                    Buy case for this listing
                  </div>
                  <span className={`conviction-pill ${String(returnCase.conviction || "watch").toLowerCase()}`}>
                    {String(returnCase.conviction || "WATCH") === "HIGH"
                      ? "Strong interest"
                      : String(returnCase.conviction || "WATCH") === "MEDIUM"
                        ? "Moderate interest"
                        : "Worth watching"}
                  </span>
                </div>
                <div className="mt-1 font-semibold leading-snug break-words">{String(returnCase.headline)}</div>
                <ul className="mt-2 space-y-1 text-sm text-[var(--muted)]">
                  {((returnCase.bullets as string[]) || []).slice(0, 2).map((b) => (
                    <li key={b}>• {b}</li>
                  ))}
                </ul>
              </div>
            ) : null}

            <div className="source-card mt-5">
              <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--muted)]">How to reach the seller</div>
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

      <section className="panel p-5">
        <PriceTrajectory
          trajectory={
            (data.market_trajectory as Parameters<typeof PriceTrajectory>[0]["trajectory"]) ||
            null
          }
        />
      </section>

      <section className="panel p-5">
        <ReturnVisual
          intel={(data.return_intelligence as AnyRec) || null}
          cases={
            ((data.scenarios_human as AnyRec[]) || scenarios || []) as never[]
          }
          entryUsd={
            returnCase.entry_usd != null ? Number(returnCase.entry_usd) : null
          }
          markUsd={returnCase.mark_usd != null ? Number(returnCase.mark_usd) : null}
          annualRate={
            Number(
              ((data.market_trajectory as AnyRec) || {}).annual_rate ??
                ((data.market_trajectory as AnyRec) || {}).annualRate,
            ) || null
          }
        />
      </section>

      <section className="grid gap-4 md:grid-cols-2">
        <InsightList title="Why this property stands out" items={whyOpp} />
        <InsightList title="Why it might still be available" items={whyStill} />
      </section>

      <section className="panel p-5">
        <h2 className="display text-xl font-semibold">What makes up the opportunity score</h2>
        <p className="mt-0.5 text-sm text-[var(--muted)]">{identity}</p>
        <p className="mt-1 text-sm text-[var(--muted)]">
          Each number below is 0–100 for this listing only. Tap any bar to see the exact inputs behind it.
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
                <p className="mt-2 text-sm leading-relaxed text-[var(--muted)]">
                  {open
                    ? String(r.why_this_number || r.plain_english || r.simple || "")
                    : firstSentence(r.why_this_number || r.plain_english || r.simple || "", 160)}
                </p>
                {open && (
                  <div className="mt-2 space-y-1 text-sm text-[var(--muted)]">
                    <div className="text-xs">{String(r.weight_display || "")}</div>
                    <ul className="space-y-1">
                      {((r.drivers as string[]) || (r.evidence as string[]) || []).slice(0, 4).map((e) => (
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
                  {String(card.level || card.knowledge_state || "")
                    .replace(/UNKNOWN/gi, "Not confirmed")
                    .replace(/ESTIMATED/gi, "Estimate")
                    .replace(/OBSERVED/gi, "From source")
                    .replace(/BLENDED/gi, "Mixed sources")
                    .replace(/_/g, " ")}
                </span>
              </div>
              <p className="mt-2 text-sm leading-relaxed">{String(card.plain_english || "No reading for this pin yet.")}</p>
              <ul className="mt-2 space-y-1 text-sm text-[var(--muted)]">
                {((card.bullets as string[]) || []).slice(0, 2).map((b) => (
                  <li key={b}>• {b}</li>
                ))}
                {addenda.slice(0, 1).map((a) => (
                  <li key={a}>• {a}</li>
                ))}
              </ul>
            </div>
          );
        })}
      </section>

      <section className="panel p-5">
        <h2 className="display text-xl font-semibold">
          Checklist before you bid · readiness{" "}
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
