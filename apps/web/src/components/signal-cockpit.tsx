"use client";

import { useMemo, useState } from "react";

type AnyRec = Record<string, unknown>;

function money(v: unknown): string {
  const n = Number(v);
  if (!Number.isFinite(n)) return "—";
  return `$${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

/** Property-unique interactive underwriting panel under the map. */
export function SignalCockpit({ cockpit }: { cockpit: AnyRec }) {
  const auction = (cockpit.auction_path as AnyRec) || null;
  const constraints = (cockpit.constraints as Record<string, AnyRec>) || {};
  const buyers = (cockpit.buyer_filters as AnyRec[]) || [];
  const pin = (cockpit.pin as AnyRec) || {};
  const model = Number(cockpit.model_value || 0);
  const opener = Number(auction?.opening_bid_usd || 0);
  const settleLow = Number(auction?.settle_low_usd || opener);
  const settle = Number(auction?.expected_settle_usd || opener);
  const settleHigh = Number(auction?.settle_high_usd || settle);
  const maxX = Math.max(model, settleHigh, opener, 1);

  const [bidGuess, setBidGuess] = useState(settle || Math.max(opener * 3, 1));
  const [focus, setFocus] = useState<"bid" | "buyers" | "constraints">("bid");

  const edge = useMemo(() => {
    if (!model) return null;
    const pct = ((bidGuess - model) / model) * 100;
    return { pct, dollars: model - bidGuess };
  }, [bidGuess, model]);

  const seed = useMemo(() => {
    const lat = Number(pin.lat || 0);
    const lon = Number(pin.lon || 0);
    return Math.abs(Math.sin(lat * 12.9898 + lon * 78.233) * 10000) % 1;
  }, [pin.lat, pin.lon]);

  const layers = [
    { key: "flood", label: "Flood", c: constraints.flood },
    { key: "wetlands", label: "Wetlands", c: constraints.wetlands },
    { key: "soil", label: "Soil", c: constraints.soil },
    { key: "transmission", label: "Power", c: constraints.transmission },
  ];

  return (
    <div className="signal-cockpit">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--muted)]">
            Not a listing card — underwriting lens
          </div>
          <h3 className="display text-lg font-semibold">{String(cockpit.title || "Acquisition signal cockpit")}</h3>
          <p className="mt-0.5 text-xs text-[var(--muted)] break-words">
            {String(cockpit.subtitle || "")}
          </p>
        </div>
        <div className="cockpit-tabs">
          {(
            [
              ["bid", "Bid path"],
              ["buyers", "Who walks"],
              ["constraints", "Constraints"],
            ] as const
          ).map(([k, label]) => (
            <button
              key={k}
              type="button"
              className={focus === k ? "active" : ""}
              onClick={() => setFocus(k)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Unique topographic fingerprint from coordinates */}
      <svg className="cockpit-fingerprint" viewBox="0 0 320 56" aria-hidden>
        {Array.from({ length: 5 }).map((_, i) => {
          const y = 12 + i * 8;
          const amp = 6 + seed * 10 + i;
          return (
            <path
              key={i}
              d={`M0 ${y} C 40 ${y - amp}, 80 ${y + amp}, 120 ${y - amp / 2} S 200 ${y + amp}, 240 ${y} S 300 ${y - amp}, 320 ${y + 2}`}
              fill="none"
              stroke={`hsla(${120 - Number(cockpit.risk || 40) * 1.2}, 45%, 38%, ${0.35 + i * 0.1})`}
              strokeWidth="1.2"
            />
          );
        })}
        <circle cx={40 + seed * 240} cy={28} r="4" fill="var(--accent)" opacity="0.85" />
      </svg>

      {focus === "bid" && (
        <div className="space-y-3">
          {auction ? (
            <>
              <p className="text-sm text-[var(--muted)] leading-relaxed">
                Opening bids are floors. Drag your max bid and see settle-adjusted edge vs the screening
                model — the number Zillow never shows.
              </p>
              <div className="bid-track" aria-hidden>
                <div className="bid-mark opener" style={{ left: `${(opener / maxX) * 100}%` }}>
                  <span>Opener</span>
                </div>
                <div className="bid-band" style={{ left: `${(settleLow / maxX) * 100}%`, width: `${((settleHigh - settleLow) / maxX) * 100}%` }} />
                <div className="bid-mark settle" style={{ left: `${(settle / maxX) * 100}%` }}>
                  <span>Settle</span>
                </div>
                {model > 0 && (
                  <div className="bid-mark model" style={{ left: `${Math.min(100, (model / maxX) * 100)}%` }}>
                    <span>Model</span>
                  </div>
                )}
              </div>
              <label className="block text-xs uppercase tracking-wide text-[var(--muted)]">
                Your max bid · {money(bidGuess)}
                <input
                  type="range"
                  className="mt-2 w-full"
                  min={opener || 1}
                  max={Math.max(model * 1.1, settleHigh * 1.2, opener * 2)}
                  step={Math.max(1, Math.round((model || settle || 1000) / 100))}
                  value={bidGuess}
                  onChange={(e) => setBidGuess(Number(e.target.value))}
                />
              </label>
              <div className="grid grid-cols-3 gap-2 text-center text-xs">
                <div className="cockpit-stat">
                  <div className="k">Opener</div>
                  <div className="v">{money(opener)}</div>
                </div>
                <div className="cockpit-stat">
                  <div className="k">Expected settle</div>
                  <div className="v">{money(settle)}</div>
                </div>
                <div className="cockpit-stat">
                  <div className="k">Your edge vs model</div>
                  <div className={`v ${edge && edge.dollars > 0 ? "pos" : "neg"}`}>
                    {edge ? `${edge.pct.toFixed(0)}%` : "—"}
                  </div>
                </div>
              </div>
              <p className="text-xs text-[var(--muted)] leading-relaxed">
                {String(auction.note || "").slice(0, 280)}
              </p>
            </>
          ) : (
            <div className="space-y-2 text-sm text-[var(--muted)]">
              <p>
                No auction opener on file — this is process / inquiry pricing. Model value{" "}
                <strong className="text-[var(--ink)]">{money(model)}</strong>.
              </p>
              <div className="grid grid-cols-3 gap-2 text-center text-xs">
                <div className="cockpit-stat">
                  <div className="k">LandSignal</div>
                  <div className="v">{Math.round(Number(cockpit.opportunity || 0))}</div>
                </div>
                <div className="cockpit-stat">
                  <div className="k">Risk</div>
                  <div className="v">{Math.round(Number(cockpit.risk || 0))}</div>
                </div>
                <div className="cockpit-stat">
                  <div className="k">Readiness</div>
                  <div className="v">{Math.round(Number(cockpit.deal_readiness || 0))}</div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {focus === "buyers" && (
        <div className="space-y-2">
          <p className="text-sm text-[var(--muted)]">
            Why capital walks — tap a filter. This is listing psychology, not marketing copy.
          </p>
          {buyers.map((b, i) => (
            <details key={i} className="cockpit-detail" open={i === 0}>
              <summary>
                <span>{String(b.label || "Buyer filter")}</span>
                {b.likelihood != null && (
                  <span className="lik">{Math.round(Number(b.likelihood) * 100)}%</span>
                )}
              </summary>
              <p className="mt-2 text-sm text-[var(--muted)]">
                {String(b.psychology || "")}
              </p>
              <ul className="mt-1 space-y-1 text-xs text-[var(--muted)]">
                {((b.evidence as string[]) || []).map((e) => (
                  <li key={e}>• {e}</li>
                ))}
              </ul>
            </details>
          ))}
          {!buyers.length && (
            <p className="text-sm text-[var(--muted)]">No strong walk-away filters extracted yet.</p>
          )}
        </div>
      )}

      {focus === "constraints" && (
        <div className="grid grid-cols-2 gap-2">
          {layers.map(({ key, label, c }) => (
            <details key={key} className="cockpit-detail">
              <summary>
                <span>{label}</span>
                <span className="lik">{String(c?.level || c?.knowledge_state || "—")}</span>
              </summary>
              <p className="mt-2 text-sm text-[var(--muted)]">
                {String(c?.plain_english || "No reading yet for this pin.")}
              </p>
            </details>
          ))}
        </div>
      )}

      <div className="mt-3 text-[11px] text-[var(--muted)]">
        Pin {pin.lat != null ? Number(pin.lat).toFixed(5) : "—"},{" "}
        {pin.lon != null ? Number(pin.lon).toFixed(5) : "—"}
        {pin.apn ? ` · ${String(pin.apn)}` : ""}
        {pin.acres != null ? ` · ${Number(pin.acres).toFixed(2)} ac` : ""}
      </div>
    </div>
  );
}
