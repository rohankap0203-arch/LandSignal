"use client";

import type { MoneyMode } from "@/lib/inflation";

export const MONEY_MODE_LABELS = {
  today: "Today's dollars",
  nominal: "Future dollars",
} as const;

export function moneyModeShort(mode: MoneyMode): string {
  return mode === "today" ? "today's dollars" : "future dollars";
}

type CompareRow = {
  label: string;
  today: number | null | undefined;
  before: number | null | undefined;
  format: (n: number) => string;
};

/** Toggle: projected future sale price vs that price in today's purchasing power. */
export function MoneyModeControl({
  mode,
  onChange,
  cpiDisplay,
  compare,
  note,
  className = "",
}: {
  mode: MoneyMode;
  onChange: (mode: MoneyMode) => void;
  cpiDisplay: string;
  compare?: CompareRow | null;
  note?: string | null;
  className?: string;
}) {
  const todayN = compare?.today != null && Number.isFinite(Number(compare.today)) ? Number(compare.today) : null;
  const beforeN =
    compare?.before != null && Number.isFinite(Number(compare.before)) ? Number(compare.before) : null;
  const hasCompare = todayN != null && beforeN != null;

  return (
    <div className={`money-mode-panel ${className}`.trim()}>
      <div className="money-mode-row" role="group" aria-label="Dollar view">
        <div className="money-mode-toggle">
          <button
            type="button"
            className={mode === "nominal" ? "is-active" : undefined}
            aria-pressed={mode === "nominal"}
            onClick={() => onChange("nominal")}
          >
            {MONEY_MODE_LABELS.nominal}
          </button>
          <button
            type="button"
            className={mode === "today" ? "is-active" : undefined}
            aria-pressed={mode === "today"}
            onClick={() => onChange("today")}
          >
            {MONEY_MODE_LABELS.today}
          </button>
        </div>
        <p className="money-mode-note">
          {note ||
            (mode === "nominal"
              ? "Projected sale price in the dollars of that future year"
              : `Same sale, measured in what money buys today (~${cpiDisplay} inflation)`)}
        </p>
      </div>

      {hasCompare && compare ? (
        <div className="money-compare" aria-live="polite">
          <div className="money-compare-k">{compare.label}</div>
          <div className="money-compare-grid">
            <button
              type="button"
              className={`money-compare-cell ${mode === "nominal" ? "is-active" : ""}`}
              onClick={() => onChange("nominal")}
            >
              <span className="money-compare-tag">{MONEY_MODE_LABELS.nominal}</span>
              <strong className="tabular-nums">{compare.format(beforeN as number)}</strong>
              <em>projected sale price</em>
            </button>
            <div className="money-compare-vs" aria-hidden>
              →
            </div>
            <button
              type="button"
              className={`money-compare-cell ${mode === "today" ? "is-active" : ""}`}
              onClick={() => onChange("today")}
            >
              <span className="money-compare-tag">{MONEY_MODE_LABELS.today}</span>
              <strong className="tabular-nums">{compare.format(todayN as number)}</strong>
              <em>purchasing power today</em>
            </button>
          </div>
          <p className="money-compare-gap">
            Inflation does <strong>not</strong> cut the sale price. It tells you whether that future
            sale still creates wealth after money loses buying power (~{cpiDisplay}).
          </p>
        </div>
      ) : null}
    </div>
  );
}
