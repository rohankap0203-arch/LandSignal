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
  noi?: number;
  annual_appreciation?: number;
  annual_appreciation_display?: string;
  purchase_price?: number;
  exit_value_by_year?: Record<string, number>;
  rent_stack_by_year?: Record<string, number>;
  cash_rent_per_acre?: number;
};

/** Hold lengths that drive both the %/yr math and future land value. */
const HOLD_YEARS = [1, 3, 5, 10, 15, 30] as const;

function money(v: unknown): string {
  const n = Number(v);
  if (!Number.isFinite(n)) return "—";
  return `$${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function caseKey(c: Case): string {
  return String(c.case_type || c.case || c.case_label || "BASE").toUpperCase();
}

function caseLabel(key: string): string {
  if (key === "BEAR" || key === "DOWNSIDE" || key === "STRESS") return "Cautious";
  if (key === "BULL" || key === "UPSIDE") return "Optimistic";
  return "Typical";
}

/** Newton IRR on yearly cashflows. */
function irrFromFlows(flows: number[]): number | null {
  if (flows.length < 2) return null;
  let r = 0.08;
  for (let i = 0; i < 60; i++) {
    let f = 0;
    let df = 0;
    for (let t = 0; t < flows.length; t++) {
      const denom = Math.pow(1 + r, t);
      f += flows[t] / denom;
      if (t > 0) df -= (t * flows[t]) / Math.pow(1 + r, t + 1);
    }
    if (Math.abs(df) < 1e-12) break;
    const next = r - f / df;
    if (!Number.isFinite(next)) break;
    if (Math.abs(next - r) < 1e-8) return next;
    r = Math.max(-0.95, Math.min(5, next));
  }
  return Number.isFinite(r) ? r : null;
}

function projectHold(purchase: number, noi: number, appr: number, years: number) {
  const exit = purchase * Math.pow(1 + appr, years);
  const rentStack = noi * years;
  const flows = [-purchase];
  for (let t = 1; t <= years; t++) {
    flows.push(t === years ? noi + exit : noi);
  }
  const irr = irrFromFlows(flows);
  const totalBack = exit + rentStack;
  const gain = totalBack - purchase;
  const gainPct = purchase > 0 ? (gain / purchase) * 100 : 0;
  return { exit, rentStack, totalBack, gain, gainPct, irr, years };
}

/** Interactive hold-return chart — selected years recompute IRR + future value. */
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
        const noi = Number(c.noi ?? (c.numbers || {}).noi ?? 0);
        const purchase = Number(c.purchase_price || entryUsd || markUsd || 0);
        const appr =
          typeof c.annual_appreciation === "number"
            ? c.annual_appreciation
            : typeof annualRate === "number"
              ? annualRate +
                (key.includes("BEAR") || key.includes("DOWN")
                  ? -0.02
                  : key.includes("BULL") || key.includes("UP")
                    ? 0.02
                    : 0)
              : 0.03;
        return {
          key,
          noi: Number.isFinite(noi) ? noi : 0,
          purchase: Number.isFinite(purchase) && purchase > 0 ? purchase : null,
          appr,
          apprDisplay: c.annual_appreciation_display || `${(appr * 100).toFixed(1)}%/yr`,
          rentPerAcre: c.cash_rent_per_acre,
          note: String(c.summary || c.plain_english || ""),
        };
      })
      .filter((r) => r.purchase != null);
  }, [cases, entryUsd, markUsd, annualRate]);

  const caseKeys = normalized.map((r) => r.key);
  const defaultCase = caseKeys.find((k) => k === "BASE") || caseKeys[0] || "BASE";
  const [activeCase, setActiveCase] = useState(defaultCase);
  const [holdYears, setHoldYears] = useState<number>(10);

  const selected = normalized.find((r) => r.key === activeCase) || normalized[0];

  const projections = useMemo(() => {
    return normalized.map((r) => {
      const p = projectHold(r.purchase!, r.noi, r.appr, holdYears);
      return { ...r, ...p };
    });
  }, [normalized, holdYears]);

  const selectedProj = projections.find((r) => r.key === activeCase) || projections[0];

  if (!normalized.length) {
    return (
      <div className="return-visual">
        <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--muted)]">
          Possible yearly return
        </div>
        <h3 className="display text-lg font-semibold">If you hold this property</h3>
        <p className="mt-1 text-sm text-[var(--muted)]">
          Not enough rent numbers yet to chart a return for a chosen hold length.
        </p>
      </div>
    );
  }

  const maxIrr = Math.max(
    12,
    ...projections.map((r) => Math.abs((r.irr ?? 0) * 100)),
  );
  const entry = selected?.purchase || entryUsd || markUsd;
  const irrPct = (selectedProj?.irr ?? 0) * 100;

  return (
    <div className="return-visual">
      <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--muted)]">
        Possible yearly return
      </div>
      <h3 className="display text-lg font-semibold">If you hold this property</h3>
      <p className="mt-1 text-sm text-[var(--muted)]">
        Case + hold length reset the %/yr and the future land value for that exact span.
        {entry ? ` Buy near ${money(entry)}.` : ""}
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

      {selectedProj && (
        <>
          <div className="return-row mt-2">
            <div className="flex items-baseline justify-between gap-2">
              <div className="font-semibold">
                {caseLabel(selectedProj.key)} · {holdYears}-year hold
              </div>
              <div className={`font-bold ${irrPct >= 0 ? "text-[var(--positive)]" : "text-[var(--danger)]"}`}>
                {irrPct.toFixed(1)}%/yr
              </div>
            </div>
            <div className="return-track">
              <div
                className={`return-fill ${irrPct >= 0 ? "pos" : "neg"}`}
                style={{ width: `${Math.max(6, (Math.abs(irrPct) / maxIrr) * 100)}%` }}
              />
            </div>
            <div className="mt-1 flex flex-wrap gap-3 text-[11px] text-[var(--muted)]">
              {selectedProj.noi > 0 ? <span>Yearly net income {money(selectedProj.noi)}</span> : null}
              <span>Land growth {selectedProj.apprDisplay}</span>
              {selectedProj.rentPerAcre != null ? (
                <span>Rent ${Number(selectedProj.rentPerAcre).toFixed(0)}/acre</span>
              ) : null}
            </div>
          </div>

          <div className="return-future mt-3">
            <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--muted)]">
              After exactly {holdYears} years · {caseLabel(selectedProj.key).toLowerCase()}
            </div>
            <div className="return-future-grid">
              <div>
                <span>Land worth</span>
                <strong>{money(selectedProj.exit)}</strong>
              </div>
              <div>
                <span>Rent along the way</span>
                <strong>{money(selectedProj.rentStack)}</strong>
              </div>
              <div>
                <span>Total back</span>
                <strong>{money(selectedProj.totalBack)}</strong>
              </div>
              <div>
                <span>Vs buy · annualized</span>
                <strong className={selectedProj.gain >= 0 ? "text-[var(--positive)]" : "text-[var(--danger)]"}>
                  {selectedProj.gain >= 0 ? "+" : ""}
                  {money(selectedProj.gain)} · {irrPct.toFixed(1)}%/yr
                </strong>
              </div>
            </div>
            <p className="mt-2 text-[11px] text-[var(--muted)] leading-relaxed">
              Land = {money(selectedProj.purchase)} × (1 + {selectedProj.apprDisplay.replace("/yr", "")})
              ^{holdYears}. Rent = yearly net × {holdYears}. %/yr is the IRR of those cashflows for this
              hold only.
            </p>
          </div>

          <div className="mt-4 space-y-2">
            <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--muted)]">
              All cases at {holdYears} years
            </div>
            {projections.map((r) => {
              const pct = (r.irr ?? 0) * 100;
              const w = Math.max(6, (Math.abs(pct) / maxIrr) * 100);
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
                      {pct.toFixed(1)}%/yr · land {money(r.exit)}
                    </span>
                  </div>
                  <div className="return-track">
                    <div
                      className={`return-fill ${pct >= 0 ? "pos" : "neg"}`}
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
