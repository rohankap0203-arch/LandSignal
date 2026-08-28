"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type MouseEvent, type KeyboardEvent } from "react";
import { AcquireRail } from "@/components/acquire-rail";
import { TrajectorySpark } from "@/components/price-trajectory";
import { LocationImagesModal, prefetchLocationImages } from "@/components/location-images-modal";
import { SignalBadge } from "@/components/signal-badge";
import type { RadarRow } from "@/lib/api";

function shortLine(text: string, max = 120): string {
  const s = (text || "").trim();
  if (!s) return "";
  const first = s.split(/(?<=[.!?])\s+/)[0] || s;
  if (first.length <= max) return first;
  const cut = first.slice(0, max);
  const at = Math.max(cut.lastIndexOf(" "), cut.lastIndexOf("·"), cut.lastIndexOf("—"));
  const base = (at > max * 0.55 ? cut.slice(0, at) : cut).trimEnd().replace(/[.,;:]+$/, "");
  return `${base}…`;
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
  const cut = s.slice(0, 28);
  const at = cut.lastIndexOf(" ");
  const base = (at > 12 ? cut.slice(0, at) : cut).trimEnd();
  return `${base}…`;
}

/** Modal title mirrors the headline (or discount line) left of the ? */
function gapHelpTitle(headline: string | null | undefined, discountDisplay: string | null | undefined): string {
  const h = (headline || "").trim();
  if (/under our value|vs our value|our value/i.test(h)) {
    return `What “${h}” means`;
  }
  const d = (discountDisplay || "").trim().replace(/\s*\(start bid[^)]*\)\s*$/i, "").trim();
  if (/vs our value|under our/i.test(d)) {
    return `What “${d}” means`;
  }
  return "What this price gap means";
}

export function PropertyCard({ row, index }: { row: RadarRow; index: number }) {
  const router = useRouter();
  const [gapHelpOpen, setGapHelpOpen] = useState(false);
  const [imagesOpen, setImagesOpen] = useState(false);
  const links = Array.isArray(row.links) ? row.links : [];
  const posting =
    links.find((l) => l.kind === "primary" && l.available !== false) ||
    (row.contact_website
      ? { label: "Open posting", url: row.contact_website, kind: "primary", available: true }
      : null);
  const findParcel =
    links.find((l) => l.kind === "lookup" && l.available !== false) ||
    (row.county || row.state
      ? {
          label: "Find this parcel",
          url: `https://www.google.com/search?q=${encodeURIComponent(
            `${row.county || ""} ${row.state || ""} parcel assessor`.trim(),
          )}`,
          kind: "lookup",
          available: true,
        }
      : null);
  const phone =
    row.contact_phone ||
    links.find((l) => l.kind === "contact" && String(l.url).startsWith("tel:"))?.label ||
    null;
  // Always prefer a real http(s) office/posting URL for the rail — never leave buyers without a path.
  const officeUrl =
    posting?.url ||
    row.contact_website ||
    links.find((l) => l.kind === "contact_web" && String(l.url || "").startsWith("http"))?.url ||
    links.find((l) => l.kind === "source" && String(l.url || "").startsWith("http"))?.url ||
    (row.contact_office || row.county
      ? `https://www.google.com/search?q=${encodeURIComponent(
          `${row.contact_office || `${row.county || ""} ${row.state || ""} treasurer`} tax sale`.trim(),
        )}`
      : null);
  const conviction = row.conviction || "WATCH";
  const blurb = shortLine(row.return_thesis || row.summary || "", 140);
  const href = `/parcels/${row.parcel_id}`;
  const gapHelp =
    row.discount_help?.trim() ||
    (row.discount_pct != null && row.estimated_value != null
      ? (() => {
          const h = (row.headline_metric || "").trim();
          const lead =
            /under our value|vs our value/i.test(h)
              ? `“${h}” means `
              : "";
          return (
            `${lead}our desktop value for this ${row.acres_display} tract in ${row.location} is about ${row.estimated_value_display}. ` +
            `The public price screen (${row.price_display}) is ${Math.abs(row.discount_pct).toFixed(0)}% ` +
            `${row.discount_pct < 0 ? "under" : "over"} that mark. That gap is a buy-edge screen — not a guaranteed close price.`
          );
        })()
      : null);
  const showGapHelp =
    Boolean(gapHelp) &&
    (/under our value|vs our value/i.test(row.headline_metric || "") ||
      /vs our value|under our/i.test(row.discount_display || ""));
  const gapTitle = gapHelpTitle(row.headline_metric, row.discount_display);

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
    router.push(href);
  }

  return (
    <article
      className="panel property-card card-clickable"
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
                aria-label={gapTitle}
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
          <span className="meta-price" title={row.ask != null && row.ask > 0 ? row.price_display : "No public price"}>
            {row.ask != null && row.ask > 0 ? shortPrice(row.price_display) : "No public price"}
          </span>
        </div>

        <div className="metric-row">
          <div className="metric">
            <div className="k">Our estimate</div>
            <div className="v">{row.estimated_value_display}</div>
          </div>
          <div className="metric">
            <div className="k">Opportunity</div>
            <div
              className="v"
              title="Global opportunity score (0–100) — same number as the intelligence report"
            >
              {Math.round(row.opportunity)}
              <span className="metric-denom">/100</span>
            </div>
          </div>
          <div className="metric">
            <div className="k">Risk</div>
            <div className="v">{Math.round(row.risk)}</div>
          </div>
          <button
            type="button"
            className="metric metric-action metric-images"
            title="Street View + nearby photos"
            aria-label="View images"
            onMouseEnter={() => prefetchLocationImages(row.parcel_id)}
            onFocus={() => prefetchLocationImages(row.parcel_id)}
            onTouchStart={() => prefetchLocationImages(row.parcel_id)}
            onClick={(e) => {
              e.stopPropagation();
              setImagesOpen(true);
            }}
          >
            <span className="metric-images-art" aria-hidden>
              <svg viewBox="0 0 120 72" preserveAspectRatio="xMidYMid slice">
                <defs>
                  <linearGradient id="viSky" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#1a3d32" />
                    <stop offset="55%" stopColor="#245844" />
                    <stop offset="100%" stopColor="#2f6b52" />
                  </linearGradient>
                </defs>
                <rect width="120" height="72" fill="url(#viSky)" />
                <circle className="metric-images-art-sun" cx="92" cy="20" r="10" />
                <path
                  className="metric-images-art-land-far"
                  d="M0 40 C22 34 36 46 54 40 C72 34 90 44 120 36 L120 72 L0 72 Z"
                />
                <path
                  className="metric-images-art-land"
                  d="M0 50 C20 44 38 56 58 50 C78 44 98 54 120 48 L120 72 L0 72 Z"
                />
              </svg>
            </span>
            <span className="metric-images-label">View images</span>
          </button>
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
          {row.has_structure ? (
            <span
              className="chip"
              title="A home, cottage, cabin, or ranch house appears to be on this parcel — not vacant land"
            >
              Property on site
            </span>
          ) : null}
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
            postingUrl={officeUrl}
            phone={typeof phone === "string" ? phone.replace(/^Call\s+/i, "") : phone}
            office={row.contact_office}
            findUrl={findParcel?.url}
            findLabel={findParcel?.label?.replace(/^Find parcel /, "ID ")}
            outreach={null}
          />
        </div>

        <div className="card-actions mt-3">
          <Link
            href={href}
            className="btn-intel"
            onClick={(e) => {
              e.stopPropagation();
            }}
          >
            Open Intelligence
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
            aria-label={gapTitle}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-3">
              <strong className="display text-lg leading-snug">{gapTitle}</strong>
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

      <LocationImagesModal
        open={imagesOpen}
        onClose={() => setImagesOpen(false)}
        title={row.property_name}
        location={row.location}
        latitude={row.latitude}
        longitude={row.longitude}
        acres={row.acres}
        parcelId={row.parcel_id}
      />
    </article>
  );
}
