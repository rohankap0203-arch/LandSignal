"use client";

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
};

function irrPct(c: Case): number | null {
  const n = c.numbers || {};
  if (typeof c.irr === "number" && Number.isFinite(c.irr)) return c.irr * (c.irr <= 1.5 ? 100 : 1);
  const raw = String(n.irr || c.irr_display || "");
  const m = raw.match(/-?[\d.]+/);
  if (!m) return null;
  const v = Number(m[0]);
  return Number.isFinite(v) ? v : null;
}

/** Parcel-specific return visual — replaces the old ROI search filter. */
export function ReturnVisual({
  cases,
  identity,
  entryLabel,
  markLabel,
}: {
  cases: Case[];
  identity: string;
  entryLabel?: string;
  markLabel?: string;
}) {
  const rows = cases
    .map((c) => ({
      label: String(c.case || c.case_label || c.case_type || "Case"),
      irr: irrPct(c),
      note: String(c.summary || c.plain_english || ""),
      noi: String((c.numbers || {}).noi || c.noi_display || ""),
      npv: String((c.numbers || {}).npv || c.npv_display || ""),
    }))
    .filter((r) => r.irr != null);

  if (!rows.length) {
    return (
      <div className="return-visual">
        <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--muted)]">Possible yearly return</div>
        <h3 className="display text-lg font-semibold">If you hold {identity}</h3>
        <p className="mt-1 text-sm text-[var(--muted)]">
          Not enough local rent numbers yet to chart a yearly %. Use the buy-price case above and check
          nearby cash rents.
        </p>
      </div>
    );
  }

  const max = Math.max(12, ...rows.map((r) => Math.abs(r.irr || 0)));

  return (
    <div className="return-visual">
      <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--muted)]">Possible yearly return</div>
      <h3 className="display text-lg font-semibold">If you hold {identity}</h3>
      <p className="mt-1 text-sm text-[var(--muted)]">
        Simple what-if cases
        {entryLabel ? ` · buy near ${entryLabel}` : ""}
        {markLabel ? ` · our value ${markLabel}` : ""}. First look only — not a promise.
      </p>
      <div className="mt-4 space-y-3">
        {rows.map((r) => {
          const w = Math.max(6, (Math.abs(r.irr || 0) / max) * 100);
          const pos = (r.irr || 0) >= 0;
          return (
            <div key={r.label} className="return-row">
              <div className="flex items-baseline justify-between gap-2">
                <div className="font-semibold">{r.label}</div>
                <div className={`font-bold ${pos ? "text-[var(--positive)]" : "text-[var(--danger)]"}`}>
                  {(r.irr || 0).toFixed(1)}%/yr
                </div>
              </div>
              <div className="return-track">
                <div
                  className={`return-fill ${pos ? "pos" : "neg"}`}
                  style={{ width: `${w}%` }}
                />
              </div>
              <p className="mt-1 text-xs text-[var(--muted)] leading-relaxed">{r.note}</p>
              {(r.noi || r.npv) && (
                <div className="mt-1 flex flex-wrap gap-3 text-[11px] text-[var(--muted)]">
                  {r.noi ? <span title="Net operating income — rent minus costs before debt">Yearly net income {r.noi}</span> : null}
                  {r.npv ? <span title="Net present value — today’s value of future cash after your buy price">Today’s net value {r.npv}</span> : null}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
