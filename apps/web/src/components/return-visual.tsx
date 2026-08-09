"use client";

import { useMemo, useState } from "react";

type Case = {
  case?: string;
  case_label?: string;
  case_type?: string;
  summary?: string;
  plain_english?: string;
  numbers?: Record<string, unknown>;
  irr?: number | string | null;
  irr_display?: string;
  noi_display?: string;
  npv_display?: string;
  noi?: number;
  annual_appreciation?: number;
  annual_appreciation_display?: string;
  purchase_price?: number;
  exit_value_by_year?: Record<string, number>;
  rent_stack_by_year?: Record<string, number>;
  cash_rent_per_acre?: number;
};

const HOLD_YEARS = [1, 3, 5, 7, 10, 15, 20, 30] as const;

function money(v: unknown): string {
  const n = Number(v);
  if (!Number.isFinite(n)) return "—";
  return `$${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function irrPct(c: Case): number | null {
  const n = c.numbers || {};
  if (typeof c.irr === "number" && Number.isFinite(c.irr)) return c.irr * (c.irr <= 1.5 ? 100 : 1);
  const raw = String(n.irr || c.irr_display || "");
  const m = raw.match(/-?[\d.]+/);
  if (!m) return null;
  const v = Number(m[0]);
  return Number.isFinite(v) ? v : null;
}

function caseKey(c: Case): string {
  return String(c.case_type || c.case || c.case_label || "BASE").toUpperCase();
}

function caseLabel(key: string): string {
  if (key === "BEAR" || key === "DOWNSIDE" || key === "STRESS") return "Cautious";
  if (key === "BULL" || key === "UPSIDE") return "Optimistic";
  return "Typical";
}

/** Interactive hold-return chart with timeframe + case toggles and future value. */
export function ReturnVisual({
  cases,
  entryUsd,
  markUsd,
  annualRate,
}: {
  cases: Case[];
  identity?: string;
  entryLabel?: string;
  markLabel?: string;
  entryUsd?: number | null;
  markUsd?: number | null;
  annualRate?: number | null;
}) {
  const normalized = useMemo(() => {
    return cases
      .map((c) => {
        const key = caseKey(c);
        const irr = irrPct(c);
        const noi = Number(c.noi ?? (c.numbers || {}).noi ?? 0);
        const purchase = Number(c.purchase_price || entryUsd || markUsd || 0);
        const appr =
          typeof c.annual_appreciation === "number"
            ? c.annual_appreciation
            : typeof annualRate === "number"
              ? annualRate + (key.includes("BEAR") || key.includes("DOWN") ? -0.02 : key.includes("BULL") || key.includes("UP") ? 0.02 : 0)
              : 0.03;
        const exits = c.exit_value_by_year || {};
        const rents = c.rent_stack_by_year || {};
        return {
          key,
          label: String(c.case || c.case_label || caseLabel(key)),
          irr,
          note: String(c.summary || c.plain_english || ""),
          noi: Number.isFinite(noi) ? noi : 0,
          purchase: Number.isFinite(purchase) && purchase > 0 ? purchase : null,
          appr,
          apprDisplay: c.annual_appreciation_display || `${(appr * 100).toFixed(1)}%/yr`,
          exits,
          rents,
          rentPerAcre: c.cash_rent_per_acre,
        };
      })
      .filter((r) => r.irr != null || r.purchase != null);
  }, [cases, entryUsd, markUsd, annualRate]);

  const caseKeys = normalized.map((r) => r.key);
  const defaultCase =
    caseKeys.find((k) => k === "BASE") || caseKeys[0] || "BASE";
  const [activeCase, setActiveCase] = useState(defaultCase);
  const [holdYears, setHoldYears] = useState<number>(10);

  const selected = normalized.find((r) => r.key === activeCase) || normalized[0];

  const projection = useMemo(() => {
    if (!selected?.purchase) return null;
    const y = holdYears;
    const exit =
      selected.exits[String(y)] ??
      selected.purchase * Math.pow(1 + selected.appr, y);
    const rentStack =
      selected.rents[String(y)] ?? (selected.noi > 0 ? selected.noi * y : 0);
    const totalBack = exit + rentStack;
    const gain = totalBack - selected.purchase;
    const gainPct = (gain / selected.purchase) * 100;
    return { exit, rentStack, totalBack, gain, gainPct, y };
  }, [selected, holdYears]);

  if (!normalized.length) {
    return (
      <div className="return-visual">
        <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--muted)]">
          Possible yearly return
        </div>
        <h3 className="display text-lg font-semibold">If you hold this property</h3>
        <p className="mt-1 text-sm text-[var(--muted)]">
          Not enough local rent numbers yet to chart a yearly %. Use the buy-price case above and
          check nearby cash rents, then come back — we’ll project future value once rents exist.
        </p>
      </div>
    );
  }

  const maxIrr = Math.max(12, ...normalized.map((r) => Math.abs(r.irr || 0)));
  const entry = selected?.purchase || entryUsd || markUsd;

  return (
    <div className="return-visual">
      <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--muted)]">
        Possible yearly return
      </div>
      <h3 className="display text-lg font-semibold">If you hold this property</h3>
      <p className="mt-1 text-sm text-[var(--muted)]">
        Pick a rent case and a hold length to see yearly % and what the land could be worth later.
        First look only — not a promise.
        {entry ? ` · modeled buy near ${money(entry)}` : ""}
        {markUsd ? ` · our value ${money(markUsd)}` : ""}.
      </p>

      <div className="traj-windows mt-3" role="tablist" aria-label="Rent case">
        {normalized.map((r) => (
          <button
            key={r.key}
            type="button"
            role="tab"
            aria-selected={activeCase === r.key}
            className={`traj-window-btn ${activeCase === r.key ? "active" : ""}`}
            onClick={() => setActiveCase(r.key)}
          >
            {caseLabel(r.key)}
          </button>
        ))}
      </div>

      <div className="traj-windows" role="tablist" aria-label="Hold length">
        {HOLD_YEARS.map((y) => (
          <button
            key={y}
            type="button"
            role="tab"
            aria-selected={holdYears === y}
            className={`traj-window-btn ${holdYears === y ? "active" : ""}`}
            onClick={() => setHoldYears(y)}
          >
            {y} yr
          </button>
        ))}
      </div>

      {selected && (
        <>
          <div className="return-row mt-2">
            <div className="flex items-baseline justify-between gap-2">
              <div className="font-semibold">
                {caseLabel(selected.key)} case · {holdYears}-year hold
              </div>
              <div
                className={`font-bold ${
                  (selected.irr || 0) >= 0 ? "text-[var(--positive)]" : "text-[var(--danger)]"
                }`}
              >
                {(selected.irr || 0).toFixed(1)}%/yr screen
              </div>
            </div>
            <div className="return-track">
              <div
                className={`return-fill ${(selected.irr || 0) >= 0 ? "pos" : "neg"}`}
                style={{ width: `${Math.max(6, (Math.abs(selected.irr || 0) / maxIrr) * 100)}%` }}
              />
            </div>
            <p className="mt-1 text-xs text-[var(--muted)] leading-relaxed">{selected.note}</p>
            <div className="mt-1 flex flex-wrap gap-3 text-[11px] text-[var(--muted)]">
              {selected.noi > 0 ? (
                <span title="Rent minus costs before debt">Yearly net income {money(selected.noi)}</span>
              ) : null}
              <span>Land value growth used {selected.apprDisplay}</span>
              {selected.rentPerAcre != null ? (
                <span>Cash rent assumption ${Number(selected.rentPerAcre).toFixed(0)}/acre</span>
              ) : null}
            </div>
          </div>

          {projection && (
            <div className="return-future mt-3">
              <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--muted)]">
                Future value in {projection.y} years · {caseLabel(selected.key).toLowerCase()} case
              </div>
              <div className="return-future-grid">
                <div>
                  <span>Land worth (if sold)</span>
                  <strong>{money(projection.exit)}</strong>
                </div>
                <div>
                  <span>Rent collected along the way</span>
                  <strong>{money(projection.rentStack)}</strong>
                </div>
                <div>
                  <span>Total back before sale costs</span>
                  <strong>{money(projection.totalBack)}</strong>
                </div>
                <div>
                  <span>Vs buy price</span>
                  <strong className={projection.gain >= 0 ? "text-[var(--positive)]" : "text-[var(--danger)]"}>
                    {projection.gain >= 0 ? "+" : ""}
                    {money(projection.gain)} ({projection.gainPct >= 0 ? "+" : ""}
                    {projection.gainPct.toFixed(0)}%)
                  </strong>
                </div>
              </div>
              <p className="mt-2 text-[11px] text-[var(--muted)] leading-relaxed">
                Land worth grows at {selected.apprDisplay} from {money(selected.purchase)}. Rent stack
                assumes today’s yearly net income stays roughly steady. Taxes, vacancy shocks, and
                selling costs can move the real number a lot — treat this as a planning dial, not a
                forecast you can bank.
              </p>
            </div>
          )}

          <div className="mt-4 space-y-2">
            <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--muted)]">
              All cases at {holdYears} years
            </div>
            {normalized.map((r) => {
              const exit =
                r.exits[String(holdYears)] ??
                (r.purchase ? r.purchase * Math.pow(1 + r.appr, holdYears) : null);
              const w = Math.max(6, (Math.abs(r.irr || 0) / maxIrr) * 100);
              return (
                <button
                  key={r.key}
                  type="button"
                  className={`return-mini ${activeCase === r.key ? "active" : ""}`}
                  onClick={() => setActiveCase(r.key)}
                >
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="font-semibold">{caseLabel(r.key)}</span>
                    <span className="tabular-nums">
                      {(r.irr || 0).toFixed(1)}%/yr
                      {exit != null ? ` · land ~${money(exit)}` : ""}
                    </span>
                  </div>
                  <div className="return-track">
                    <div
                      className={`return-fill ${(r.irr || 0) >= 0 ? "pos" : "neg"}`}
                      style={{ width: `${w}%` }}
                    />
                  </div>
                </button>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
