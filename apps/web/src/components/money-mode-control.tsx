"use client";

import type { MoneyMode } from "@/lib/inflation";

export const MONEY_MODE_LABELS = {
  today: "After inflation",
  nominal: "Before inflation",
} as const;

export function moneyModeShort(mode: MoneyMode): string {
  return mode === "today" ? "after inflation" : "before inflation";
}

type CompareRow = {
  label: string;
  today: number | null | undefined;
  before: number | null | undefined;
  format: (n: number) => string;
};

/** Toggle + dual comparison for inflation-adjusted vs unadjusted future dollars. */
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
      <div className="money-mode-row" role="group" aria-label="Inflation view">
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
              ? `Buying power: future $ ÷ (~${cpiDisplay})^years — same sale, today’s dollars`
              : `Raw future sticker — no ~${cpiDisplay} CPI haircut`)}
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
              <em>what those $ buy today</em>
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
              <em>future sticker</em>
            </button>
          </div>
          {gap != null && gap > 0 ? (
            <p className="money-compare-gap">
              Same sale. After inflation asks what those future dollars buy{" "}
              <strong>today</strong> (~{gap}% less purchasing power at ~{cpiDisplay}). It is not
              “the land became worthless.”
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
