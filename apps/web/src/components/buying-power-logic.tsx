"use client";

import { useState } from "react";

function money(v: number): string {
  return `$${Math.round(v).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function pct(n: number, digits = 1): string {
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(digits)}%`;
}

type Props = {
  variant: "hold" | "land";
  years: number;
  cpi: number;
  cpiDisplay: string;
  purchaseUsd?: number | null;
  markUsd?: number | null;
  futureNominal?: number | null;
  futureToday?: number | null;
  totalBackToday?: number | null;
  totalBackNominal?: number | null;
  /** When false / missing with a teaser ask, label as value — not a $100 “purchase”. */
  purchaseLabel?: string | null;
  treatAsPurchase?: boolean | null;
  className?: string;
};

/**
 * On-the-nose inflation explainer: sale price vs purchasing power.
 * Inflation does not lower the sale price — it changes what those dollars buy.
 *
 * Caps absurd %-gains when a teaser CAD ask was (incorrectly) treated as purchase.
 * Prefer mark / value-today when purchase is a non-credible fraction of value.
 */
export function BuyingPowerLogic({
  variant,
  years,
  cpi,
  cpiDisplay,
  purchaseUsd,
  markUsd,
  futureNominal,
  futureToday,
  totalBackToday,
  totalBackNominal,
  purchaseLabel,
  treatAsPurchase,
  className = "",
}: Props) {
  const [open, setOpen] = useState(false);
  if (!(years >= 1) || futureNominal == null || futureToday == null) return null;

  const rawBuy =
    purchaseUsd != null && Number.isFinite(Number(purchaseUsd)) ? Number(purchaseUsd) : null;
  const mark = markUsd != null && Number.isFinite(Number(markUsd)) ? Number(markUsd) : null;

  // Guardrail: teaser entry vs mark would mint lottery %-gains (e.g. $100 → mark path).
  const buyLooksTeaser =
    rawBuy != null &&
    mark != null &&
    mark > 0 &&
    (rawBuy / mark < 0.15 || rawBuy < 2500);
  const usePurchase =
    treatAsPurchase !== false && rawBuy != null && !buyLooksTeaser ? rawBuy : null;
  const start = usePurchase ?? mark ?? rawBuy;
  if (start == null || !(start > 0)) return null;

  const saleFuture = Number(futureNominal);
  const saleToday$ = Number(futureToday);
  const endFuture =
    variant === "hold" && totalBackNominal != null && Number.isFinite(Number(totalBackNominal))
      ? Number(totalBackNominal)
      : saleFuture;
  const endToday$ =
    variant === "hold" && totalBackToday != null && Number.isFinite(Number(totalBackToday))
      ? Number(totalBackToday)
      : saleToday$;

  const nominalGain = endFuture - start;
  const nominalGainPct = (endFuture / start - 1) * 100;
  const realGain = endToday$ - start;
  let realGainPct = (endToday$ / start - 1) * 100;
  const GAIN_CAP = 500; // display cap — beyond this the entry was not market-comparable
  const realCapped = Math.abs(realGainPct) > GAIN_CAP;
  if (realCapped) {
    realGainPct = Math.sign(realGainPct) * GAIN_CAP;
  }
  const beatInflation = realGain >= 0;
  const cpiRisePct = (Math.pow(1 + cpi, years) - 1) * 100;

  const headline = realCapped
    ? beatInflation
      ? `Yes — purchasing power is up (display capped at ${GAIN_CAP}% — entry not a clean market buy).`
      : `Purchasing power is down (display capped at ${GAIN_CAP}%).`
    : beatInflation
      ? `Yes — purchasing power is up about ${pct(realGainPct, 0).replace("+", "")}.`
      : `On paper you may gain dollars, but purchasing power is down about ${pct(Math.abs(realGainPct), 0).replace("+", "")}.`;

  const startLabel =
    purchaseLabel ||
    (usePurchase != null ? "Purchase today" : "Value today");
  const endLabel = variant === "hold" ? `Money back · ${years} yr` : `Projected · ${years} yr`;

  const toggle = () => setOpen((o) => !o);

  return (
    <div className={`buy-power ${open ? "is-open" : ""} ${className}`.trim()}>
      {/* Collapsed: whole card is the hit target (mouse + finger). Expanded: header toggles. */}
      <div
        className="buy-power-hit"
        role="button"
        tabIndex={0}
        aria-expanded={open}
        aria-label="Did this beat inflation?"
        onClick={toggle}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            toggle();
          }
        }}
      >
        <div className="buy-power-toggle">
          <span className="buy-power-k">Did this beat inflation?</span>
          <span className={`buy-power-verdict ${beatInflation ? "is-pos" : "is-neg"}`}>
            {beatInflation ? "Yes" : "No"}
          </span>
          <span className="buy-power-chev" aria-hidden>
            {open ? "▾" : "▸"}
          </span>
        </div>
        {!open ? <p className="buy-power-teaser">{headline}</p> : null}
      </div>
      {open ? (
        <div className="buy-power-body">
          <p className="buy-power-head">{headline}</p>

          <div className="buy-power-table" role="table" aria-label="Sale price vs purchasing power">
            <div className="buy-power-row" role="row">
              <span role="cell">{startLabel}</span>
              <strong className="tabular-nums" role="cell">
                {money(start)}
              </strong>
            </div>
            <div className="buy-power-row" role="row">
              <span role="cell">{endLabel}</span>
              <strong className="tabular-nums" role="cell">
                {money(endFuture)}
              </strong>
            </div>
            <div className="buy-power-row" role="row">
              <span role="cell">Gain · future $</span>
              <strong
                className={`tabular-nums ${nominalGain >= 0 ? "is-pos" : "is-neg"}`}
                role="cell"
              >
                {pct(nominalGainPct, 0)}
                <small>
                  {nominalGain >= 0 ? "+" : ""}
                  {money(nominalGain)}
                </small>
              </strong>
            </div>
            <div className="buy-power-row" role="row">
              <span role="cell">Inflation</span>
              <strong className="tabular-nums" role="cell">
                ~{cpiDisplay}
                <small>
                  ~{cpiRisePct.toFixed(0)}% over {years} yr
                </small>
              </strong>
            </div>
            <div className="buy-power-row" role="row">
              <span role="cell">In today’s dollars</span>
              <strong className="tabular-nums" role="cell">
                {money(endToday$)}
              </strong>
            </div>
            <div className="buy-power-row buy-power-row--focus" role="row">
              <span role="cell">Real wealth</span>
              <strong
                className={`tabular-nums ${beatInflation ? "is-pos" : "is-neg"}`}
                role="cell"
              >
                {pct(realGainPct)}
                {realCapped ? <small>capped</small> : null}
              </strong>
            </div>
          </div>

          <ul className="buy-power-points">
            <li>
              <span className="buy-power-pin" aria-hidden />
              <span>
                <strong>Inflation does not lower the sale price.</strong> It changes what those
                dollars can buy.
              </span>
            </li>
            <li>
              <span className="buy-power-pin" aria-hidden />
              <span>
                <strong>Other factors still matter.</strong> Local demand, site limits, rates,
                taxes, and hold costs are already in the projected price.
              </span>
            </li>
            <li>
              <span className="buy-power-pin" aria-hidden />
              <span>
                <strong>Opportunity score is separate.</strong> It measures today’s buy versus our
                value — not this long-hold inflation check.
              </span>
            </li>
          </ul>
        </div>
      ) : null}
    </div>
  );
}
