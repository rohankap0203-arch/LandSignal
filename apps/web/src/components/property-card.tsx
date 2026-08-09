"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type MouseEvent, type KeyboardEvent } from "react";
import { AcquireRail } from "@/components/acquire-rail";
import { TrajectorySpark } from "@/components/price-trajectory";
import { SignalBadge } from "@/components/signal-badge";
import type { RadarRow } from "@/lib/api";

function shortLine(text: string, max = 120): string {
  const s = (text || "").trim();
  if (!s) return "";
  const first = s.split(/(?<=[.!?])\s+/)[0] || s;
  return first.length > max ? first.slice(0, max - 1).trimEnd() + "…" : first;
}

function convictionLabel(c: string): string {
  if (c === "HIGH") return "Strong interest";
  if (c === "MEDIUM") return "Moderate interest";
  return "Worth watching";
}

function shortPrice(display: string): string {
  const s = (display || "").trim();
  if (!s) return "No public price";
  if (s.length <= 28) return s;
  return s.slice(0, 27).trimEnd() + "…";
}

export function PropertyCard({ row, index }: { row: RadarRow; index: number }) {
  const router = useRouter();
  const [intelPending, setIntelPending] = useState(false);
  const [gapHelpOpen, setGapHelpOpen] = useState(false);
  const posting =
    row.links.find((l) => l.kind === "primary" && l.available !== false) ||
    (row.contact_website
      ? { label: "Open posting", url: row.contact_website, kind: "primary", available: true }
      : null);
  const findParcel = row.links.find((l) => l.kind === "lookup" && l.available !== false) || null;
  const phone =
    row.contact_phone ||
    row.links.find((l) => l.kind === "contact" && String(l.url).startsWith("tel:"))?.label ||
    null;
  const conviction = row.conviction || "WATCH";
  const blurb = shortLine(row.return_thesis || row.summary || "", 140);
  const href = `/parcels/${row.parcel_id}`;
  const gapHelp =
    row.discount_help?.trim() ||
    (row.discount_pct != null && row.estimated_value != null
      ? `Our desktop value for this ${row.acres_display} tract in ${row.location} is about ${row.estimated_value_display}. The public price screen (${row.price_display}) is ${Math.abs(row.discount_pct).toFixed(0)}% ${row.discount_pct < 0 ? "under" : "over"} that mark. That gap is a buy-edge screen — not a guaranteed close price.`
      : null);
  const showGapHelp =
    Boolean(gapHelp) &&
    (/under our value|vs our value/i.test(row.headline_metric || "") ||
      /vs our value|under our/i.test(row.discount_display || ""));

  useEffect(() => {
    if (!gapHelpOpen) return;
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.key === "Escape") setGapHelpOpen(false);
    };
    const timer = window.setTimeout(() => setGapHelpOpen(false), 12000);
    window.addEventListener("keydown", onKey);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("keydown", onKey);
    };
  }, [gapHelpOpen]);

  function openIntel(e?: MouseEvent | KeyboardEvent) {
    if (e) {
      const t = e.target as HTMLElement | null;
      if (t?.closest("a, button, input, select, textarea, label")) return;
    }
    setIntelPending(true);
    router.push(href);
  }

  return (
    <article
      className={`panel property-card card-clickable ${intelPending ? "pending" : ""}`}
      style={{ animationDelay: `${Math.min(index, 8) * 40}ms` }}
      onClick={openIntel}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          openIntel(e);
        }
      }}
      role="link"
      tabIndex={0}
      aria-label={`Open intelligence for ${row.property_name}`}
    >
      <div className="card-media">
        <div>
          <SignalBadge signal={row.signal} />
          <div
            className="mt-3 text-xs uppercase tracking-[0.08em] text-white/75"
            title={
              row.provider_id === "public_tax_sale"
                ? "Sold by the county after unpaid property taxes — not a normal listing"
                : row.provider_id === "blm_lpad"
                  ? "Federal Bureau of Land Management disposal parcel"
                  : "Public land inventory channel"
            }
          >
            {row.provider_label}
          </div>
          <div className="headline-with-help mt-1">
            <div className="display text-2xl font-semibold leading-snug break-words">{row.headline_metric}</div>
            {showGapHelp ? (
              <button
                type="button"
                className={`help-q headline-help-q ${gapHelpOpen ? "on" : ""}`}
                aria-label="What under our value means"
                aria-expanded={gapHelpOpen}
                onClick={(e) => {
                  e.stopPropagation();
                  setGapHelpOpen(true);
                }}
              >
                ?
              </button>
            ) : null}
          </div>
        </div>
        <div>
          <div className="text-sm text-white/80 break-words">{row.location}</div>
          <div className="mt-1 text-lg font-semibold break-words">{row.acres_display}</div>
        </div>
      </div>

      <div className="card-body">
        <h2 className="display text-xl font-semibold leading-snug break-words">
          <Link
            href={href}
            className="hover:text-[var(--brand-soft)]"
            onClick={(e) => {
              e.stopPropagation();
              setIntelPending(true);
            }}
          >
            {row.property_name}
          </Link>
        </h2>
        {blurb ? (
          <p className="card-thesis mt-1.5 text-sm leading-snug text-[var(--muted)] break-words">{blurb}</p>
        ) : null}
        {row.scout_note ? (
          <p className="mt-1 text-xs leading-snug text-[var(--ink)] break-words">
            <span className="text-[var(--muted)]">Why this file · </span>
            {row.scout_note}
          </p>
        ) : null}

        <div className="card-meta-line mt-2" title="Interest · filter match · listed price">
          <span className={`conviction-pill ${conviction.toLowerCase()}`}>{convictionLabel(conviction)}</span>
          <span className="meta-match" title="How well this matches your filters (0–100)">
            Match {Math.round(row.fit_score ?? row.opportunity)}
          </span>
          <span className="meta-price" title={row.price_display}>
            {shortPrice(row.price_display)}
          </span>
        </div>

        <div className="metric-row">
          <div className="metric">
            <div className="k">Our estimate</div>
            <div className="v">{row.estimated_value_display}</div>
          </div>
          <div className="metric">
            <div className="k">Opportunity</div>
            <div className="v">{Math.round(row.opportunity)}</div>
          </div>
          <div className="metric">
            <div className="k">Risk</div>
            <div className="v">{Math.round(row.risk)}</div>
          </div>
        </div>

        <div className="card-chip-line mt-2">
          {row.freshness_hours != null && Number(row.freshness_hours) <= 72 ? (
            <span className="chip new-chip" title="Seen in inventory within the last 72 hours">
              New
            </span>
          ) : null}
          {(row.signal === "EXCEPTIONAL" || row.signal === "STRONG") && (
            <span className="chip new-chip" title="Engine-ranked buy candidate — not a typical MLS find">
              Scout pick
            </span>
          )}
          <span className="chip">{row.discount_display}</span>
          <span className="chip">{row.best_strategy_label}</span>
          <span className="chip" title="Detail page builds a year-by-year path from soil, flood, growth, channel, and more">
            Multi-factor path
          </span>
        </div>

        <TrajectorySpark
          values={row.trajectory_sparkline}
          label={row.trajectory_label}
          cagr={row.trajectory_cagr_5y}
        />

        {row.match_reasons?.length ? (
          <ul className="reasons">
            {row.match_reasons.slice(0, 2).map((reason) => (
              <li key={reason}>{shortLine(reason, 100)}</li>
            ))}
          </ul>
        ) : null}

        <div onClick={(e) => e.stopPropagation()}>
          <AcquireRail
            className="mt-3"
            postingUrl={posting?.url}
            phone={phone}
            office={row.contact_office}
            findUrl={findParcel?.url}
            findLabel={findParcel?.label?.replace(/^Find parcel /, "ID ")}
          />
        </div>

        <div className="card-actions mt-3">
          <Link
            href={href}
            className={`btn-intel ${intelPending ? "pending" : ""}`}
            onClick={(e) => {
              e.stopPropagation();
              setIntelPending(true);
            }}
          >
            {intelPending ? "Opening…" : "Open Intelligence"}
          </Link>
        </div>
      </div>

      {gapHelpOpen && gapHelp ? (
        <div
          className="help-modal-backdrop"
          role="presentation"
          onClick={(e) => {
            e.stopPropagation();
            setGapHelpOpen(false);
          }}
        >
          <div
            className="help-modal"
            role="dialog"
            aria-modal="true"
            aria-label="What under our value means"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-3">
              <strong className="display text-lg leading-snug">What “under our value” means here</strong>
              <button
                type="button"
                className="help-q on"
                aria-label="Close"
                onClick={(e) => {
                  e.stopPropagation();
                  setGapHelpOpen(false);
                }}
              >
                ×
              </button>
            </div>
            <p className="mt-2 text-sm leading-relaxed text-[var(--muted)]">{gapHelp}</p>
            <p className="mt-3 text-xs text-[var(--muted)]">
              {row.property_name} · {row.location}
            </p>
          </div>
        </div>
      ) : null}
    </article>
  );
}
