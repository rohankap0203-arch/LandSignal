"use client";

import { useState } from "react";

function shortMoney(v: number): string {
  const a = Math.abs(v);
  if (a >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
  if (a >= 10_000) return `$${Math.round(v / 1000)}k`;
  if (a >= 1000) return `$${(v / 1000).toFixed(1)}k`;
  return `$${Math.round(v).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

type Props = {
  /** Hold cashflow vs land mark path. */
  variant: "hold" | "land";
  years: number;
  cpi: number;
  cpiDisplay: string;
  /** What you pay today (hold) — optional on land path. */
  purchaseUsd?: number | null;
  /** Today's land mark. */
  markUsd?: number | null;
  /** Future sticker before CPI haircut. */
  futureNominal?: number | null;
  /** Future sticker in today's buying power. */
  futureToday?: number | null;
  /** Hold only: total back after inflation. */
  totalBackToday?: number | null;
  /** Hold only: total back − purchase in today's $. */
  gainToday?: number | null;
  /** Live owned-land pace, e.g. "2.4%/yr". */
  paceDisplay?: string | null;
  className?: string;
};

/**
 * Plain-English buying-power logic — answers why After inflation can fall
 * while Opportunity (buy edge) stays high.
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
  gainToday,
  paceDisplay,
  className = "",
}: Props) {
  const [open, setOpen] = useState(years >= 10);
  if (!(years >= 1) || futureNominal == null || futureToday == null) return null;

  const buy = purchaseUsd != null && Number.isFinite(Number(purchaseUsd)) ? Number(purchaseUsd) : null;
  const mark = markUsd != null && Number.isFinite(Number(markUsd)) ? Number(markUsd) : null;
  const before = Number(futureNominal);
  const after = Number(futureToday);
  const gain =
    gainToday != null && Number.isFinite(Number(gainToday))
      ? Number(gainToday)
      : buy != null && variant === "hold" && totalBackToday != null
        ? Number(totalBackToday) - buy
        : null;
  const haircutPct = before > 0 ? Math.round(((before - after) / before) * 100) : null;
  const stickerUp = before > (mark ?? buy ?? 0);
  const powerSoftVsMark = mark != null ? after < mark : false;
  const beatBuyReal = gain != null ? gain >= 0 : after > (buy ?? Infinity);

  const headline =
    variant === "hold"
      ? beatBuyReal
        ? powerSoftVsMark
          ? "Cheap buy can still win — even if dirt’s buying power drifts vs CPI."
          : "In today’s dollars, you still come out ahead of what you paid."
        : stickerUp
          ? "You sell for more future $ than you paid — CPI says those $ buy less."
          : "Real hold is soft here — pace / carry / exit aren’t beating CPI."
      : stickerUp && powerSoftVsMark
        ? "Sticker rises; buying power softens. That’s CPI — not the dirt rotting."
        : powerSoftVsMark
          ? "After inflation asks what future land $ buy today — not “will anyone pay less then.”"
          : "Pace is outrunning the CPI screen on this window.";

  const formula = `After inflation = future $ ÷ ${(1 + cpi).toFixed(3)}^${years}`;

  return (
    <div className={`buy-power ${className}`.trim()}>
      <button
        type="button"
        className={`buy-power-toggle ${open ? "is-open" : ""}`}
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        <span className="buy-power-k">Buying power · does After inflation mean I lose?</span>
        <span className="buy-power-chev" aria-hidden>
          {open ? "▾" : "▸"}
        </span>
      </button>
      {!open ? (
        <p className="buy-power-teaser">{headline}</p>
      ) : (
        <div className="buy-power-body">
          <p className="buy-power-head">{headline}</p>
          <div className="buy-power-rails" aria-label="Dollar anchors">
            {buy != null ? (
              <div>
                <span>You pay</span>
                <strong className="tabular-nums">{shortMoney(buy)}</strong>
                <em>today</em>
              </div>
            ) : null}
            {mark != null ? (
              <div>
                <span>Today’s mark</span>
                <strong className="tabular-nums">{shortMoney(mark)}</strong>
                <em>our land value</em>
              </div>
            ) : null}
            <div>
              <span>{years} yr sticker</span>
              <strong className="tabular-nums">{shortMoney(before)}</strong>
              <em>before inflation</em>
            </div>
            <div>
              <span>{years} yr buying power</span>
              <strong className="tabular-nums">{shortMoney(after)}</strong>
              <em>after inflation</em>
            </div>
          </div>
          <ul className="buy-power-points">
            <li>
              <strong>Same sale, two reads.</strong> Before = dollars printed in year {years}. After =
              those dollars in today’s grocery / lumber buying power
              {haircutPct != null && haircutPct > 0 ? ` (~${haircutPct}% CPI haircut)` : ""}.
            </li>
            <li>
              <strong>Math:</strong> <code>{formula}</code>
              {paceDisplay ? (
                <>
                  {" "}
                  · owned-land pace ~{paceDisplay} vs CPI ~{cpiDisplay}
                  {Number.isFinite(cpi) && paceDisplay.includes("%")
                    ? " — when pace ≈ CPI, After inflation looks flat/soft even as the sticker climbs."
                    : "."}
                </>
              ) : (
                <> · long-run CPI screen ~{cpiDisplay}.</>
              )}
            </li>
            {variant === "hold" ? (
              <li>
                <strong>Opportunity ≠ this line.</strong> Opportunity scores the{" "}
                <em>buy edge vs our value today</em>
                {buy != null && mark != null && mark > buy
                  ? ` (here ~${shortMoney(mark - buy)} under mark)`
                  : ""}
                . It is not a promise the dirt outruns CPI for {years} years. Judge the hold with{" "}
                <em>vs buy after inflation</em>
                {gain != null
                  ? ` (${gain >= 0 ? "+" : ""}${shortMoney(gain)} here)`
                  : ""}
                .
              </li>
            ) : (
              <li>
                <strong>Opportunity ≠ this line.</strong> Land value path is the{" "}
                <em>area mark</em> over time. Opportunity is whether today’s ask / opener is cheap vs
                that mark — a separate dial from whether the mark beats CPI far out.
              </li>
            )}
            {variant === "hold" && beatBuyReal && powerSoftVsMark ? (
              <li>
                <strong>Why both can be true:</strong> buying power of the mark can drift under
                today’s mark while a discounted entry still beats what you paid in real terms.
              </li>
            ) : null}
          </ul>
        </div>
      )}
    </div>
  );
}
