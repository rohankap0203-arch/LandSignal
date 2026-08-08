"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { LandLoader } from "@/components/land-loader";
import { ScoreBar } from "@/components/score-bar";
import { SignalBadge } from "@/components/signal-badge";
import { SignalCockpit } from "@/components/signal-cockpit";
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
  const [memoLoading, setMemoLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ddOpen, setDdOpen] = useState<Record<string, boolean>>({});
  const [watched, setWatched] = useState(false);
  const [watchMsg, setWatchMsg] = useState("");
  const [openCard, setOpenCard] = useState<string | null>("soil");

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
        detail="Pulling soils, flood, wetlands, auction settle math, and buyer-psychology filters for this pin."
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
  const liveLinks = links.filter((l) => l.available !== false);
  const sellerLink =
    liveLinks.find((l) => l.kind === "primary" && l.available !== false) ||
    (sourcing.website
      ? { label: "Open source posting", url: String(sourcing.website), kind: "primary", available: true }
      : null);
  const phoneLink =
    liveLinks.find((l) => l.kind === "contact" && String(l.url).startsWith("tel:")) ||
    (sourcing.phone
      ? {
          label: String(sourcing.phone),
          url: `tel:${String(sourcing.phone).replace(/-/g, "")}`,
          kind: "contact",
          available: true,
        }
      : null);

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
        <div className="panel px-4 py-3 text-sm text-[var(--muted)]">
          {watchMsg || String(brief.watch_hint)}
        </div>
      )}

      <section className="panel overflow-hidden">
        <div className="grid gap-0 lg:grid-cols-[1.05fr_0.95fr]">
          <div className="p-6">
            <div className="flex flex-wrap items-center gap-2">
              {score && <SignalBadge signal={score.signal as string} />}
              <span className="rounded-full bg-[var(--bg-soft)] px-3 py-1 text-xs font-semibold">
                LIVE PUBLIC SOURCE
              </span>
            </div>
            <h1 className="display mt-3 text-3xl font-semibold leading-tight break-words">
              {(listing?.title as string) || (parcel.apn as string)}
            </h1>
            <p className="mt-2 text-[var(--muted)] break-words">
              {parcel.county as string}, {parcel.state as string}
              {parcel.acreage != null ? ` · ${Number(parcel.acreage).toFixed(2)} acres` : ""}
              {parcel.apn ? ` · ${String(parcel.apn)}` : ""}
            </p>
            <p className="mt-4 max-w-2xl text-[15px] leading-relaxed text-[var(--ink)] break-words">
              {String(listing?.description || "No description published by source.")}
            </p>

            <div className="mt-5 grid gap-4">
              <ScoreBar label="LandSignal" value={Number(score?.opportunity || 0)} hint={story.landsignal} />
              <ScoreBar label="Risk" value={Number(score?.risk || 0)} invert hint={story.risk} />
              <ScoreBar
                label="Confidence (evidence completeness)"
                value={Number(score?.confidence || 0)}
                hint={story.confidence}
              />
            </div>

            <div className="mt-5 grid grid-cols-2 gap-3">
              <Stat label={String(price?.label || "Price")} value={String(price?.display || "No public ask")} />
              <Stat label="Deal readiness" value={`${Number(score?.deal_readiness || 0).toFixed(0)}/100`} />
            </div>

            <div className="source-card mt-5">
              <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--muted)]">Where this came from</div>
              <div className="font-semibold break-words">{String(sourcing.source_name || "Public GIS feed")}</div>
              <div className="mt-1 text-sm text-[var(--muted)] break-words">
                Seller / office: {String(sourcing.office || "See source site")}
                {sourcing.phone ? ` · ${String(sourcing.phone)}` : ""}
              </div>
              {sourcing.how_to_buy ? (
                <p className="mt-2 text-xs leading-relaxed text-[var(--muted)]">{String(sourcing.how_to_buy)}</p>
              ) : null}
            </div>

            <div className="mt-4 flex flex-wrap gap-2">
              {sellerLink && (
                <a className="btn-posting" href={sellerLink.url} target="_blank" rel="noreferrer">
                  Open posting
                </a>
              )}
              {phoneLink && (
                <a className="btn-call" href={phoneLink.url}>
                  {String(phoneLink.label).startsWith("Call ")
                    ? phoneLink.label
                    : `Call ${phoneLink.label}`}
                </a>
              )}
              {links
                .filter(
                  (l) =>
                    l.url !== sellerLink?.url &&
                    l.url !== phoneLink?.url &&
                    l.kind !== "map",
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
        <LandLoader compact label="Composing investment memo…" detail="Weighing score, constraints, and diligence gaps." />
      )}

      <section className="grid gap-4 md:grid-cols-2">
        <InteractiveList
          title="Why this opportunity"
          items={whyOpp.map((x) => ({
            title: String(x.headline || x),
            body: String(x.detail || ""),
          }))}
        />
        <InteractiveList
          title="Why it may still be available"
          items={whyStill.map((x) => ({
            title: String(x.headline || x),
            body: String(x.detail || ""),
          }))}
        />
      </section>

      <section className="panel p-5">
        <h2 className="display text-xl font-semibold">Backed rating breakdown</h2>
        <p className="mt-1 text-sm text-[var(--muted)]">
          Tap a category. Each bar is this parcel’s own evidence — not generic marketing copy.
        </p>
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          {ratings.map((r) => {
            const scoreN = Number(r.score || 0);
            const key = String(r.key);
            const open = openCard === `r-${key}`;
            return (
              <button
                key={key}
                type="button"
                className="rounded-2xl bg-[var(--bg-soft)] p-4 text-left transition hover:ring-1 hover:ring-[var(--brand-soft)]"
                onClick={() => setOpenCard(open ? null : `r-${key}`)}
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
                <p className="mt-2 text-sm text-[var(--muted)]">{String(r.simple || "")}</p>
                {open && (
                  <div className="mt-2 space-y-1 text-sm">
                    <p className="font-medium">{String(r.plain_english || "")}</p>
                    <div className="text-xs text-[var(--muted)]">
                      {String(r.weight_display || `${r.weight_pct}% of score`)} · {String(r.knowledge_state)}
                    </div>
                    <ul className="space-y-1 text-[var(--muted)]">
                      {((r.evidence as string[]) || []).map((e) => (
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
          const addenda = (brief[addKey] as string[]) || [];
          const open = openCard === key;
          return (
            <button
              key={key}
              type="button"
              className="panel p-4 text-left"
              onClick={() => setOpenCard(open ? null : key)}
            >
              <div className="flex items-center justify-between gap-2">
                <h3 className="font-semibold">{String(card.title || key)}</h3>
                <span className="text-[10px] uppercase tracking-wide text-[var(--muted)]">
                  {String(card.level || card.knowledge_state || "")}
                </span>
              </div>
              <p className="mt-2 text-sm leading-relaxed">{String(card.plain_english || "No reading yet.")}</p>
              {open && (
                <div className="mt-2 space-y-1 text-sm text-[var(--muted)]">
                  {((card.bullets as string[]) || []).map((b) => (
                    <p key={b}>• {b}</p>
                  ))}
                  {addenda.map((a) => (
                    <p key={a}>• {a}</p>
                  ))}
                  <p className="text-[11px]">
                    Source: {String(card.source || "n/a")}
                    {card.confidence != null ? ` · evidence ${String(card.confidence)}` : ""}
                  </p>
                </div>
              )}
              <div className="mt-2 text-xs text-[var(--brand)]">{open ? "Hide details" : "Show details"}</div>
            </button>
          );
        })}
      </section>

      <section className="panel p-5">
        <h2 className="display text-xl font-semibold">Hold-period farmland scenarios</h2>
        <p className="mt-1 text-sm text-[var(--muted)]">
          Parcel-specific what-ifs. Tap a case. These are screens, not promises.
        </p>
        <div className="mt-4 grid gap-3 md:grid-cols-3">
          {scenarios.map((s, i) => {
            const key = String(s.case || s.case_type || i);
            const open = openCard === `sc-${key}`;
            const numbers = (s.numbers as AnyRec) || s;
            return (
              <button
                key={key}
                type="button"
                className="rounded-2xl bg-[var(--bg-soft)] p-4 text-left"
                onClick={() => setOpenCard(open ? null : `sc-${key}`)}
              >
                <div className="font-semibold">{String(s.case || s.case_label || s.case_type)}</div>
                <p className="mt-2 text-sm text-[var(--muted)]">{String(s.summary || s.plain_english || "")}</p>
                {open && (
                  <dl className="mt-3 grid gap-2 text-sm">
                    {(
                      [
                        ["Yearly income (NOI)", numbers.noi || numbers.noi_display],
                        ["Return (IRR)", numbers.irr || numbers.irr_display],
                        ["Value today (NPV)", numbers.npv || numbers.npv_display],
                        ["Breakeven land price", numbers.breakeven || numbers.breakeven_display],
                      ] as const
                    ).map(([k, v]) =>
                      v ? (
                        <div key={k} className="flex justify-between gap-2">
                          <dt className="text-[var(--muted)]">{k}</dt>
                          <dd className="font-semibold">{String(v)}</dd>
                        </div>
                      ) : null,
                    )}
                  </dl>
                )}
              </button>
            );
          })}
        </div>
      </section>

      <section className="panel p-5">
        <h2 className="display text-xl font-semibold">
          Manual due diligence · readiness {Number(score?.deal_readiness || 0).toFixed(0)}/100
        </h2>
        <p className="mt-1 text-sm text-[var(--muted)]">
          Tap each step for why it matters on this exact parcel and how to start.
        </p>
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
                    <p>
                      <strong className="text-[var(--ink)]">For this property:</strong>{" "}
                      {String(item.parcel_note || item.why_it_matters)}
                    </p>
                    <p>
                      <strong className="text-[var(--ink)]">How to start:</strong> {String(item.how_to_start)}
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

function InteractiveList({
  title,
  items,
}: {
  title: string;
  items: Array<{ title: string; body: string }>;
}) {
  const [open, setOpen] = useState(0);
  return (
    <div className="panel p-5">
      <h2 className="display text-xl font-semibold">{title}</h2>
      <div className="mt-3 space-y-2">
        {items.map((item, i) => (
          <button
            key={`${item.title}-${i}`}
            type="button"
            className="w-full rounded-2xl bg-[var(--bg-soft)] p-3 text-left"
            onClick={() => setOpen(open === i ? -1 : i)}
          >
            <div className="font-semibold">{item.title}</div>
            {open === i && item.body && (
              <p className="mt-2 text-sm leading-relaxed text-[var(--muted)]">{item.body}</p>
            )}
          </button>
        ))}
        {!items.length && <p className="text-sm text-[var(--muted)]">No narrative for this parcel yet.</p>}
      </div>
    </div>
  );
}
