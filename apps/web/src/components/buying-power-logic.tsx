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
  /** Hold cashflow vs land mark path. */
  variant: "hold" | "land";
  years: number;
  cpi: number;
  cpiDisplay: string;
  /** What you pay today (hold). */
  purchaseUsd?: number | null;
  /** Today's land mark / starting value. */
  markUsd?: number | null;
  /** Projected future sale / mark in future dollars. */
  futureNominal?: number | null;
  /** That same future amount in today's purchasing power. */
  futureToday?: number | null;
  /** Hold: total back after inflation (exit + rent in today's $). */
  totalBackToday?: number | null;
  /** Hold: total back before inflation. */
  totalBackNominal?: number | null;
  className?: string;
};

/**
 * On-the-nose inflation explainer: sale price vs purchasing power.
 * Inflation does not lower the sale price — it changes what those dollars buy.
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
  className = "",
}: Props) {
  const [open, setOpen] = useState(years >= 5);
  if (!(years >= 1) || futureNominal == null || futureToday == null) return null;

  const buy =
    purchaseUsd != null && Number.isFinite(Number(purchaseUsd)) ? Number(purchaseUsd) : null;
  const mark = markUsd != null && Number.isFinite(Number(markUsd)) ? Number(markUsd) : null;
  const start = buy ?? mark;
  if (start == null || !(start > 0)) return null;

  const saleFuture = Number(futureNominal);
  const saleToday$ = Number(futureToday);
  // For hold return, prefer total-back when present (includes rent / carry).
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
  const realGainPct = (endToday$ / start - 1) * 100;
  const beatInflation = realGain >= 0;
  const cpiRisePct = (Math.pow(1 + cpi, years) - 1) * 100;

  const headline = beatInflation
    ? `Yes — after inflation, purchasing power is up about ${pct(realGainPct, 0).replace("+", "")}.`
    : `You may make dollars on paper, but purchasing power is down about ${pct(Math.abs(realGainPct), 0).replace("+", "")}.`;

  const startLabel = buy != null ? "Purchase today" : "Value today";
  const endLabel =
    variant === "hold" ? `Money back in ${years} yr` : `Projected value in ${years} yr`;

  return (
    <div className={`buy-power ${className}`.trim()}>
      <button
        type="button"
        className={`buy-power-toggle ${open ? "is-open" : ""}`}
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        <span className="buy-power-k">Did this beat inflation?</span>
        <span className={`buy-power-verdict ${beatInflation ? "is-pos" : "is-neg"}`}>
          {beatInflation ? "Yes" : "No"}
        </span>
        <span className="buy-power-chev" aria-hidden>
          {open ? "▾" : "▸"}
        </span>
      </button>
      {!open ? (
        <p className="buy-power-teaser">{headline}</p>
      ) : (
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
              <span role="cell">Gain in future dollars</span>
              <strong
                className={`tabular-nums ${nominalGain >= 0 ? "is-pos" : "is-neg"}`}
                role="cell"
              >
                {pct(nominalGainPct)} ({nominalGain >= 0 ? "+" : ""}
                {money(nominalGain)})
              </strong>
            </div>
            <div className="buy-power-row" role="row">
              <span role="cell">Inflation assumption</span>
              <strong className="tabular-nums" role="cell">
                ~{cpiDisplay} (~{cpiRisePct.toFixed(0)}% over {years} yr)
              </strong>
            </div>
            <div className="buy-power-row" role="row">
              <span role="cell">{money(endFuture)} in today’s dollars</span>
              <strong className="tabular-nums" role="cell">
                ~{money(endToday$)}
              </strong>
            </div>
            <div className="buy-power-row buy-power-row--focus" role="row">
              <span role="cell">Real wealth (purchasing power)</span>
              <strong
                className={`tabular-nums ${beatInflation ? "is-pos" : "is-neg"}`}
                role="cell"
              >
                {pct(realGainPct)}
              </strong>
            </div>
          </div>

          <ul className="buy-power-points">
            <li>
              <strong>Inflation does not lower the sale price.</strong> It changes what those
              dollars can buy. The {money(endFuture)} figure is the projected future price
              {variant === "hold" ? " (sale + rent along the way)" : ""}. ~{money(endToday$)} is
              that same money measured in today’s purchasing power.
            </li>
            <li>
              <strong>Other factors still matter.</strong> The projected price already reflects
              local demand, site limits, rates stress cases, taxes, and hold costs — not inflation
              alone. Inflation here is only the purchasing-power check:{" "}
              <code>
                {money(endFuture)} ÷ {(1 + cpi).toFixed(3)}^{years}
              </code>
              .
            </li>
            {buy != null && mark != null && mark > buy ? (
              <li>
                <strong>Opportunity score is separate.</strong> It measures whether today’s buy
                looks cheap versus our value (~{money(mark)}), not whether this hold beats
                inflation for {years} years.
              </li>
            ) : (
              <li>
                <strong>Opportunity score is separate.</strong> It measures today’s buy versus our
                value — not whether this long hold beats inflation.
              </li>
            )}
          </ul>
        </div>
      )}
    </div>
  );
}
