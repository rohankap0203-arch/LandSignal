"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { AcquireRail, type OutreachPlaybook } from "@/components/acquire-rail";
import { LandLoader } from "@/components/land-loader";
import { LandViewerModal } from "@/components/land-viewer-modal";
import { CatalystSimulator } from "@/components/catalyst-simulator";
import { PriceTrajectory } from "@/components/price-trajectory";
import { ReturnVisual } from "@/components/return-visual";
import { ScoreBar } from "@/components/score-bar";
import { SignalBadge } from "@/components/signal-badge";
import { SignalCockpit } from "@/components/signal-cockpit";
import { landsignalApi, type ActionLink } from "@/lib/api";
import type { MoneyMode } from "@/lib/inflation";

const ParcelMap = dynamic(() => import("@/components/parcel-map").then((m) => m.ParcelMap), {
  ssr: false,
});

type AnyRec = Record<string, unknown>;

function firstSentence(text: unknown, max = 140): string {
  const s = String(text || "").trim();
  if (!s) return "";
  const cut = s.split(/(?<=[.!?])\s+/)[0] || s;
  if (cut.length <= max) return cut;
  const head = cut.slice(0, max);
  const at = Math.max(head.lastIndexOf(" "), head.lastIndexOf("·"), head.lastIndexOf("—"));
  const base = (at > max * 0.55 ? head.slice(0, at) : head).trimEnd().replace(/[.,;:]+$/, "");
  return `${base}…`;
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

function WatchEyeButton({
  watched,
  onToggle,
}: {
  watched: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      className={`watch-eye ${watched ? "on" : ""}`}
      onClick={onToggle}
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
  );
}

export default function ParcelIntelligencePage() {
  const params = useParams<{ id: string }>();
  const [data, setData] = useState<AnyRec | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [watched, setWatched] = useState(false);
  const [watchMsg, setWatchMsg] = useState("");
  const [openRating, setOpenRating] = useState<string | null>(null);
  const [landViewerOpen, setLandViewerOpen] = useState(false);
  const [moneyMode, setMoneyMode] = useState<MoneyMode>("today");

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
  const ratings = ((data.rating_breakdown as AnyRec[]) || []).filter(
    (r) => String(r.key || "") !== "hbu_optionality",
  );
  const land = (data.land_readouts as Record<string, AnyRec>) || {};
  const brief = (data.brief as AnyRec) || {};
  const cockpit = (data.cockpit as AnyRec) || {};
  const sourcing = (data.sourcing as AnyRec) || ((cockpit.source as AnyRec) || {});
  const whyOpp = (brief.why_opportunity as AnyRec[]) || [];
  const whyStill = (brief.why_still_available as AnyRec[]) || [];
  const scenarios = (brief.scenario_cards as AnyRec[]) || (data.scenarios_human as AnyRec[]) || [];
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

      <section className="panel">
        <div className="p-6 pb-4">
          <div className="intel-topbar">
            <div className="intel-topbar-left">
              {score ? <SignalBadge signal={score.signal as string} /> : null}
              <WatchEyeButton watched={watched} onToggle={toggleWatch} />
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

          <div className="next-process mt-4">
            <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--muted)]">
              Three steps from here
            </div>
            <ol className="next-process-list mt-2">
              <li className="next-process-step">
                <span className="next-process-num" aria-hidden>
                  1
                </span>
                <div className="min-w-0">
                  <div className="font-semibold text-sm">Learn this land</div>
                    <p className="next-process-note">
                      Skim value, return, why this land, score parts, land checks.
                    </p>
                  <button
                    type="button"
                    className="next-process-action"
                    onClick={() => {
                      const el = document.getElementById("sec-read-start");
                      if (!el) return;
                      // Land below the sticky header + scroll-to chips (slightly lower than before).
                      const top = el.getBoundingClientRect().top + window.scrollY - 56;
                      window.scrollTo({ top, behavior: "smooth" });
                    }}
                  >
                    Start reading ↓
                  </button>
                </div>
              </li>
              <li className="next-process-step">
                <span className="next-process-num" aria-hidden>
                  2
                </span>
                <div className="min-w-0">
                  <div className="font-semibold text-sm">
                    {watched ? "On your watchlist" : "Watchlist if interested"}
                  </div>
                  <p className="next-process-note">
                    {watched ? "Saved — come back anytime." : "Save it if it still feels like a fit."}
                  </p>
                  <button type="button" className="next-process-action" onClick={toggleWatch}>
                    {watched ? "Remove" : "Add to watchlist"}
                  </button>
                </div>
              </li>
              <li className="next-process-step">
                <span className="next-process-num" aria-hidden>
                  3
                </span>
                <div className="min-w-0">
                  <div className="font-semibold text-sm">Contact the seller</div>
                  <p className="next-process-note">
                    Reach out, then open What to say / Look-for.
                  </p>
                  <button
                    type="button"
                    className="next-process-action"
                    onClick={() =>
                      document
                        .getElementById("sec-reach")
                        ?.scrollIntoView({ behavior: "smooth", block: "start" })
                    }
                  >
                    Contact & advice ↓
                  </button>
                </div>
              </li>
            </ol>
          </div>
        </div>

        <div className="border-t border-[var(--line)]">
          <nav id="sec-scroll-to" className="scroll-to scroll-mt-20" aria-label="Scroll to">
            <div className="scroll-to-label">Scroll-to</div>
            <div className="scroll-to-row">
              {[
                { id: "sec-bidding", label: "Bidding by price" },
                { id: "sec-value", label: "Land value" },
                { id: "sec-return", label: "Hold return" },
                { id: "sec-catalyst", label: "Future scenarios" },
                { id: "sec-why", label: "Why this land" },
                { id: "sec-score", label: "Score parts" },
                { id: "sec-land", label: "Land checks" },
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
          <div id="sec-read-start" className="scroll-mt-16">
          <ParcelMap
            latitude={parcel.latitude as number}
            longitude={parcel.longitude as number}
            polygon={parcel.polygon as number[][][]}
            title={listing?.title as string}
            height={280}
            onExpand={() => setLandViewerOpen(true)}
          />
          </div>
          <LandViewerModal
            open={landViewerOpen}
            onClose={() => setLandViewerOpen(false)}
            title={String(listing?.title || "Parcel")}
            location={[parcel.county, parcel.state].filter(Boolean).join(", ") || null}
            acresDisplay={
              parcel.acres != null && Number.isFinite(Number(parcel.acres))
                ? `${Number(parcel.acres).toLocaleString(undefined, { maximumFractionDigits: 2 })} ac`
                : null
            }
            priceDisplay={
              listing?.asking_price != null
                ? `$${Number(listing.asking_price).toLocaleString()}`
                : null
            }
            latitude={parcel.latitude as number}
            longitude={parcel.longitude as number}
            polygon={parcel.polygon as number[][][]}
            parcelId={String(parcel.id || params.id)}
          />
        </div>

        <div className="border-t border-[var(--line)] p-6">
          <div className="grid gap-3">
            <ScoreBar
              label="Opportunity score"
              value={Number(score?.opportunity || 0)}
              hint={String(
                (oppDrive.hint as string) ||
                  oppDrive.verdict ||
                  "Tap to see how this stacks up across the site",
              )}
              verdict={String(oppDrive.verdict || "")}
              bullets={(oppDrive.bullets as string[]) || []}
              standings={
                (oppDrive.standings as Parameters<typeof ScoreBar>[0]["standings"]) || null
              }
            />
            <ScoreBar
              label="Risk"
              value={Number(score?.risk || 0)}
              invert
              hint={String(
                (riskDrive.hint as string) ||
                  riskDrive.verdict ||
                  "Tap for what could go wrong",
              )}
              verdict={String(riskDrive.verdict || "")}
              bullets={(riskDrive.bullets as string[]) || []}
              standings={
                (riskDrive.standings as Parameters<typeof ScoreBar>[0]["standings"]) || null
              }
            />
            <ScoreBar
              label="How complete the file is"
              value={Number(score?.confidence || 0)}
              hint={String(
                (confDrive.hint as string) ||
                  confDrive.verdict ||
                  "Tap to see what’s filled in",
              )}
              verdict={String(confDrive.verdict || "")}
              bullets={(confDrive.bullets as string[]) || []}
              standings={
                (confDrive.standings as Parameters<typeof ScoreBar>[0]["standings"]) || null
              }
            />
          </div>

          <div className="mt-5">
            <PriceStat
              label={String(price?.label || "Price")}
              value={String(price?.display || "No public price yet")}
              kind={String((price as AnyRec)?.kind || "")}
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
              <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--muted)]">
                Buy case for this listing
              </div>
              <div className="mt-1 font-semibold leading-snug break-words">{String(returnCase.headline)}</div>
              <ul className="mt-2 space-y-1 text-sm text-[var(--muted)]">
                {((returnCase.bullets as string[]) || []).slice(0, 2).map((b) => (
                  <li key={b}>• {b}</li>
                ))}
              </ul>
            </div>
          ) : null}

          <div id="sec-reach" className="source-card mt-5 scroll-mt-20">
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
      </section>

      <section id="sec-bidding" className="panel p-5 scroll-mt-20">
        <SignalCockpit cockpit={cockpit} />
      </section>

      <section id="sec-value" className="panel p-5 scroll-mt-20">
        <PriceTrajectory
          trajectory={
            (data.market_trajectory as Parameters<typeof PriceTrajectory>[0]["trajectory"]) ||
            null
          }
          moneyMode={moneyMode}
          onMoneyModeChange={setMoneyMode}
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
          moneyMode={moneyMode}
          onMoneyModeChange={setMoneyMode}
        />
      </section>

      <CatalystSimulator
        parcelId={String(params.id)}
        engine={(data.catalyst_engine as Parameters<typeof CatalystSimulator>[0]["engine"]) || null}
      />

      <section id="sec-why" className="insight-pair scroll-mt-20">
        <InsightList
          eyebrow="Scout edge"
          title="What makes this one worth opening"
          items={whyOpp}
        />
        <InsightList
          eyebrow="Still on the board"
          title="Why it hasn’t been scooped yet"
          items={whyStill}
        />
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
          <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--muted)]">
            Ground truth
          </div>
          <h2 className="display text-lg font-semibold">Checks that move the score</h2>
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

/** Peel "$1,013 start" / "~$29,228–$56,208 likely finish" into amount + role. */
function peelBidFace(raw: string): { amount: string; role: "start" | "finish" | null } {
  const t = raw.trim();
  if (/\blikely finish\b/i.test(t)) {
    return { amount: t.replace(/\s*likely finish\s*$/i, "").trim(), role: "finish" };
  }
  if (/\bstart\b/i.test(t)) {
    return { amount: t.replace(/\s*start\s*$/i, "").trim(), role: "start" };
  }
  return { amount: t, role: null };
}

/** Starting bid → likely finish — admit-one ticket (above Buy case).
 *  Auction / tax-sale floors only — retail asks and unpriced estimates stay plain. */
function PriceStat({ label, value, kind }: { label: string; value: string; kind?: string }) {
  const isBid =
    kind === "minimum_bid" ||
    /starting bid/i.test(label) ||
    (/\bstart\b/i.test(value) && /likely finish/i.test(value));
  if (!isBid) return <Stat label={label} value={value} />;

  const parts = value.split(/\s·\s/).map((p) => p.trim()).filter(Boolean);
  const faces = parts.map(peelBidFace);
  const start = faces.find((f) => f.role === "start") || (faces[0] ? { ...faces[0], role: "start" as const } : null);
  const finish =
    faces.find((f) => f.role === "finish") ||
    (faces.length >= 2 ? { amount: faces.slice(1).map((f) => f.amount).join(" · "), role: "finish" as const } : null);

  return (
    <div className="bid-ticket" aria-label={`${label}: ${value}`}>
      <div className="bid-ticket-stub" aria-hidden>
        <span className="bid-ticket-stub-k">BID</span>
      </div>
      <span className="bid-ticket-perf" aria-hidden />
      <div className="bid-ticket-main">
        {start && finish ? (
          <div className="bid-ticket-prices">
            <div className="bid-ticket-cell is-start">
              <span className="bid-ticket-tag">START</span>
              <span className="bid-ticket-val">{start.amount}</span>
            </div>
            <span className="bid-ticket-split" aria-hidden />
            <div className="bid-ticket-cell is-finish">
              <span className="bid-ticket-tag">LIKELY FINISH</span>
              <span className="bid-ticket-val">{finish.amount}</span>
            </div>
          </div>
        ) : (
          <span className="bid-ticket-val">{value}</span>
        )}
      </div>
    </div>
  );
}

function InsightList({
  title,
  items,
  eyebrow,
}: {
  title: string;
  items: AnyRec[];
  eyebrow?: string;
}) {
  const [open, setOpen] = useState<number>(-1);
  const rows = (items || []).filter((item) => {
    const headline = String(item?.headline || item || "").trim();
    return Boolean(headline);
  });
  return (
    <div className="panel insight-interactive">
      <div className="insight-interactive-inner">
        {eyebrow ? (
          <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--muted)]">{eyebrow}</div>
        ) : null}
        <h2 className="display text-lg font-semibold leading-snug">{title}</h2>
        <div className="insight-list">
          {rows.map((item, i) => {
            const active = open === i;
            const detail = String(item.detail || "").trim();
            return (
              <button
                key={`${String(item.headline || item)}-${i}`}
                type="button"
                className={`insight-item${active ? " is-open" : ""}`}
                onClick={() => setOpen(active ? -1 : i)}
              >
                <div className="insight-item-head">
                  <div className="font-semibold text-sm leading-snug">{String(item.headline || item)}</div>
                  <span className="insight-item-toggle" aria-hidden>
                    {active ? "−" : "+"}
                  </span>
                </div>
                {active && detail ? (
                  <p className="insight-item-detail">{detail}</p>
                ) : null}
              </button>
            );
          })}
          {!rows.length ? (
            <p className="text-sm text-[var(--muted)]">No parcel-specific narrative yet.</p>
          ) : null}
        </div>
      </div>
    </div>
  );
}
