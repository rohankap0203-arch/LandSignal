"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { AcquireRail, type OutreachPlaybook } from "@/components/acquire-rail";
import { AskYourselfTypewriter } from "@/components/ask-yourself-typewriter";
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
  const askYourself = (brief.ask_yourself as AnyRec) || null;
  const story = (brief.score_story as Record<string, string>) || {};
  const returnCase = (brief.return_case as AnyRec) || {};
  const drivers = (data.score_drivers as AnyRec) || {};
  const oppDrive = (drivers.opportunity as AnyRec) || {};
  const riskDrive = (drivers.risk as AnyRec) || {};
  const confDrive = (drivers.confidence as AnyRec) || {};

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
                <button
                  type="button"
                  className={`watch-eye ${watched ? "on" : ""}`}
                  onClick={toggleWatch}
                  title={watched ? "Remove from watchlist" : "Add to watchlist"}
                  aria-label={watched ? "Remove from watchlist" : "Add to watchlist"}
                  aria-pressed={watched}
                >
                  <svg viewBox="0 0 24 24" aria-hidden>
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
                <span className="rounded-full bg-[var(--bg-soft)] px-3 py-1 text-xs font-semibold">
                  {String(sourcing.source_name || "Public source")}
                </span>
              </div>
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

            {((drivers.buy_lens as AnyRec) || {}).next_step ? (
              <div className="guide-next mt-4">
                <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--muted)]">
                  Clear next step
                </div>
                <p className="mt-1 text-sm font-medium leading-snug">
                  {String((drivers.buy_lens as AnyRec).next_step)}
                </p>
              </div>
            ) : null}

            <div className="mt-5 grid gap-3">
              <ScoreBar
                label="Opportunity score"
                value={Number(score?.opportunity || 0)}
                hint={String(oppDrive.verdict || "Tap for why this file scored here")}
                verdict={String(oppDrive.verdict || "")}
                bullets={(oppDrive.bullets as string[]) || []}
              />
              <ScoreBar
                label="Risk"
                value={Number(score?.risk || 0)}
                invert
                hint={String(riskDrive.verdict || "Tap for what could go wrong")}
                verdict={String(riskDrive.verdict || "")}
                bullets={(riskDrive.bullets as string[]) || []}
              />
              <ScoreBar
                label="How complete the file is"
                value={Number(score?.confidence || 0)}
                hint={String(confDrive.verdict || "Tap to see what’s filled in")}
                verdict={String(confDrive.verdict || "")}
                bullets={(confDrive.bullets as string[]) || []}
              />
            </div>

            <div className="mt-5 grid grid-cols-2 gap-3">
              <Stat label={String(price?.label || "Price")} value={String(price?.display || "No public price yet")} />
              <Stat
                label="Basics already on file"
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
                outreach={(data.outreach as OutreachPlaybook) || null}
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
            <nav className="scroll-to" aria-label="Scroll to">
              <div className="scroll-to-label">Scroll-to</div>
              <div className="scroll-to-row">
                {[
                  { id: "sec-value", label: "Value path" },
                  { id: "sec-return", label: "Return" },
                  { id: "sec-why", label: "Why buy / why open" },
                  { id: "sec-score", label: "Score parts" },
                  { id: "sec-land", label: "Land checks" },
                  { id: "sec-ask", label: "Ask yourself" },
                ].map((s) => (
                  <button
                    key={s.id}
                    type="button"
                    className="scroll-to-btn"
                    onClick={() =>
                      document.getElementById(s.id)?.scrollIntoView({ behavior: "smooth", block: "start" })
                    }
                  >
                    {s.label}
                  </button>
                ))}
              </div>
            </nav>
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

      <section id="sec-value" className="panel p-5 scroll-mt-20">
        <PriceTrajectory
          trajectory={
            (data.market_trajectory as Parameters<typeof PriceTrajectory>[0]["trajectory"]) ||
            null
          }
        />
      </section>

      <section id="sec-return" className="panel p-5 scroll-mt-20">
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

      <section id="sec-why" className="grid gap-4 md:grid-cols-2 scroll-mt-20">
        <InsightList title="Why this property stands out" items={whyOpp} />
        <InsightList title="Why it might still be available" items={whyStill} />
      </section>

      <section id="sec-score" className="panel p-5 scroll-mt-20">
        <h2 className="display text-xl font-semibold">What makes up the opportunity score</h2>
        <p className="mt-0.5 text-sm text-[var(--muted)]">{identity}</p>
        <div className="mt-3 grid gap-2 md:grid-cols-2">
          {ratings.map((r) => {
            const scoreN = Number(r.score || 0);
            const key = String(r.key);
            const open = openRating === key;
            return (
              <button
                key={key}
                type="button"
                className={`rounded-xl bg-[var(--bg-soft)] p-3 text-left transition hover:ring-1 hover:ring-[var(--brand-soft)] ${open ? "ring-1 ring-[var(--brand-soft)]" : ""}`}
                onClick={() => setOpenRating(open ? null : key)}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="font-semibold text-sm">{String(r.label)}</div>
                  <div className="text-sm font-semibold whitespace-nowrap">
                    {String(r.score_display || `${scoreN.toFixed(0)}/100`)}
                  </div>
                </div>
                <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-[var(--bg-elevated)]">
                  <div
                    className="h-full rounded-full transition-all"
                    style={{
                      width: `${Math.max(4, Math.min(100, scoreN))}%`,
                      background: `hsl(${scoreN * 1.2} 65% 42%)`,
                    }}
                  />
                </div>
                <p className="mt-1.5 text-xs leading-snug text-[var(--muted)]">
                  {open
                    ? String(r.why_this_number || r.plain_english || r.simple || "")
                    : firstSentence(r.why_this_number || r.plain_english || r.simple || "", 110)}
                </p>
                {open && (
                  <ul className="mt-1.5 space-y-0.5 text-xs text-[var(--muted)]">
                    {((r.drivers as string[]) || (r.evidence as string[]) || []).slice(0, 3).map((e) => (
                      <li key={e}>• {e}</li>
                    ))}
                  </ul>
                )}
              </button>
            );
          })}
        </div>
      </section>

      <section id="sec-land" className="scroll-mt-20">
        <div className="mb-2">
          <h2 className="display text-lg font-semibold">Land checks that move the needle</h2>
        </div>
        <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-4">
          {(
            [
              "soil",
              "flood",
              "wetlands",
              "transmission",
              "access",
              "slope",
              "growth",
              "resale",
            ] as const
          ).map((key) => {
            const card = land[key] || {};
            const level = String(card.level || card.knowledge_state || "")
              .replace(/KnowledgeState\./gi, "")
              .replace(/UNKNOWN/gi, "Not confirmed")
              .replace(/KNOWN/gi, "Known")
              .replace(/ESTIMATED/gi, "Estimate")
              .replace(/OBSERVED/gi, "From source")
              .replace(/BLENDED/gi, "Mixed")
              .replace(/TEMPORARILY_UNAVAILABLE/gi, "Unavailable")
              .replace(/_/g, " ");
            return (
              <details key={key} className="panel land-compact group">
                <summary className="cursor-pointer list-none">
                  <div className="flex items-center justify-between gap-2">
                    <h3 className="font-semibold text-sm">{String(card.title || key)}</h3>
                    <span className="text-[10px] uppercase tracking-wide text-[var(--muted)]">{level}</span>
                  </div>
                  <p className="mt-1 text-[var(--ink)]">
                    {firstSentence(card.plain_english || "No reading for this pin yet.", 110)}
                  </p>
                </summary>
                <ul className="mt-1 space-y-0.5">
                  {((card.bullets as string[]) || []).slice(0, 2).map((b) => (
                    <li key={b}>• {b}</li>
                  ))}
                </ul>
              </details>
            );
          })}
        </div>
      </section>

      {askYourself?.question ? (
        <section id="sec-ask" className="panel ask-yourself scroll-mt-20 p-5 md:p-7">
          <div className="text-[10px] uppercase tracking-[0.16em] text-[var(--muted)]">
            {String(askYourself.label || "Ask yourself")}
          </div>
          <AskYourselfTypewriter
            question={String(askYourself.question)}
            aftertaste={askYourself.aftertaste ? String(askYourself.aftertaste) : null}
            holdMs={7000}
          />
        </section>
      ) : null}

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
    <div className="panel p-4 insight-interactive">
      <h2 className="display text-lg font-semibold">{title}</h2>
      <div className="mt-2 space-y-1.5">
        {items.map((item, i) => {
          const active = open === i;
          return (
            <button
              key={`${String(item.headline || item)}-${i}`}
              type="button"
              className={`w-full rounded-xl bg-[var(--bg-soft)] p-2.5 text-left ${active ? "active" : ""}`}
              onClick={() => setOpen(active ? -1 : i)}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="font-semibold text-sm leading-snug">{String(item.headline || item)}</div>
                <span className="text-[10px] text-[var(--muted)] shrink-0">{active ? "−" : "+"}</span>
              </div>
              {active && item.detail ? (
                <p className="mt-1.5 text-xs leading-relaxed text-[var(--muted)]">{String(item.detail)}</p>
              ) : !active && item.detail ? (
                <p className="mt-1 text-xs text-[var(--muted)] line-clamp-1">{String(item.detail)}</p>
              ) : null}
            </button>
          );
        })}
        {!items.length && <p className="text-sm text-[var(--muted)]">No parcel-specific narrative yet.</p>}
      </div>
    </div>
  );
}
