"use client";

import type { MoneyMode } from "@/lib/inflation";

export const MONEY_MODE_LABELS = {
  today: "Today’s $",
  nominal: "Before inflation",
} as const;

export function moneyModeShort(mode: MoneyMode): string {
  return mode === "today" ? "today’s $" : "before inflation";
}

type CompareRow = {
  label: string;
  today: number | null | undefined;
  before: number | null | undefined;
  format: (n: number) => string;
};

/** Toggle + in-your-face dual comparison for inflation views. */
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
  const gap =
    hasCompare && beforeN > 0 ? Math.round(((beforeN - (todayN as number)) / beforeN) * 100) : null;

  return (
    <div className={`money-mode-panel ${className}`.trim()}>
      <div className="money-mode-row" role="group" aria-label="Dollar view">
        <div className="money-mode-toggle">
          <button
            type="button"
            className={mode === "today" ? "is-active" : undefined}
            aria-pressed={mode === "today"}
            onClick={() => onChange("today")}
          >
            {MONEY_MODE_LABELS.today}
          </button>
          <button
            type="button"
            className={mode === "nominal" ? "is-active" : undefined}
            aria-pressed={mode === "nominal"}
            onClick={() => onChange("nominal")}
          >
            {MONEY_MODE_LABELS.nominal}
          </button>
        </div>
        <p className="money-mode-note">
          {note ||
            (mode === "today"
              ? `Buying power after ~${cpiDisplay} inflation`
              : `Raw future dollars · ignores ~${cpiDisplay} inflation`)}
        </p>
      </div>

      {hasCompare && compare ? (
        <div className="money-compare" aria-live="polite">
          <div className="money-compare-k">{compare.label}</div>
          <div className="money-compare-grid">
            <button
              type="button"
              className={`money-compare-cell ${mode === "today" ? "is-active" : ""}`}
              onClick={() => onChange("today")}
            >
              <span className="money-compare-tag">{MONEY_MODE_LABELS.today}</span>
              <strong className="tabular-nums">{compare.format(todayN as number)}</strong>
              <em>what it buys now</em>
            </button>
            <div className="money-compare-vs" aria-hidden>
              vs
            </div>
            <button
              type="button"
              className={`money-compare-cell ${mode === "nominal" ? "is-active" : ""}`}
              onClick={() => onChange("nominal")}
            >
              <span className="money-compare-tag">{MONEY_MODE_LABELS.nominal}</span>
              <strong className="tabular-nums">{compare.format(beforeN as number)}</strong>
              <em>raw future number</em>
            </button>
          </div>
          {gap != null && gap > 0 ? (
            <p className="money-compare-gap">
              Inflation eats about <strong>{gap}%</strong> of that future dollar figure at ~{cpiDisplay}.
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
