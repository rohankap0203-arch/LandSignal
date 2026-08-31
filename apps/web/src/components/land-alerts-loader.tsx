"use client";

import { useEffect, useMemo, useState } from "react";

type LotVerdict = "pending" | "match" | "pass";

type LotCard = {
  id: number;
  state: string;
  acres: string;
  price: string;
  verdict: LotVerdict;
};

const STATES = ["FL", "TX", "GA", "NC", "AZ", "CO", "OR", "TN", "VA", "OK", "NM", "MT"];
const ACRES = ["4.2 ac", "12 ac", "28 ac", "5.5 ac", "41 ac", "9 ac", "18 ac", "63 ac", "3.1 ac", "22 ac"];
const PRICES = ["$48k", "$120k", "$86k", "$210k", "$64k", "$175k", "$95k", "$310k", "$39k", "$142k"];

function MagnifierIcon({ size = 64 }: { size?: number }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} aria-hidden className="la-solo-glass-svg">
      <circle cx="10.5" cy="10.5" r="6.25" fill="rgba(244,250,246,0.12)" stroke="currentColor" strokeWidth="1.85" />
      <circle cx="10.5" cy="10.5" r="3.4" fill="none" stroke="currentColor" strokeWidth="1.1" opacity="0.45" />
      <line
        x1="15.15"
        y1="15.15"
        x2="21"
        y2="21"
        stroke="currentColor"
        strokeWidth="2.4"
        strokeLinecap="round"
      />
    </svg>
  );
}

function makeLot(id: number, verdict: LotVerdict = "pending"): LotCard {
  return {
    id,
    state: STATES[id % STATES.length],
    acres: ACRES[id % ACRES.length],
    price: PRICES[id % PRICES.length],
    verdict,
  };
}

const PHASES = [
  "Scanning land lots",
  "Checking acres & price",
  "Scoring against your profile",
  "Approving the strong fits",
] as const;

/** Solo magnifying-glass scan — inspects lots, approves some, passes others. */
export function LandAlertsLoader({
  label,
  detail,
  mode = "matching",
}: {
  label?: string;
  detail?: string;
  mode?: "boot" | "matching";
}) {
  const [dots, setDots] = useState(1);
  const [phase, setPhase] = useState(0);
  const [tick, setTick] = useState(0);
  const [matched, setMatched] = useState(0);
  const [passed, setPassed] = useState(0);
  const [lots, setLots] = useState<LotCard[]>(() =>
    [0, 1, 2, 3, 4].map((i) => makeLot(i, i === 0 ? "pending" : "pending")),
  );

  useEffect(() => {
    const t = window.setInterval(() => setDots((d) => (d % 3) + 1), 380);
    return () => window.clearInterval(t);
  }, []);

  useEffect(() => {
    if (mode !== "matching") return;
    const t = window.setInterval(() => setPhase((p) => (p + 1) % PHASES.length), 1500);
    return () => window.clearInterval(t);
  }, [mode]);

  // Advance the conveyor: inspect current front lot → match or pass → slide next in.
  useEffect(() => {
    if (mode !== "matching") return;
    let cancelled = false;
    let id = 5;
    let localMatched = 0;
    let localPassed = 0;

    const step = () => {
      if (cancelled) return;
      // Decide on the active (first pending) lot — ~45% match for a lively mix.
      const approve = Math.random() < 0.45;
      setLots((prev) => {
        const next = prev.map((lot, i) => {
          if (i !== 0 || lot.verdict !== "pending") return lot;
          return { ...lot, verdict: approve ? "match" : "pass" };
        });
        return next;
      });
      if (approve) {
        localMatched += 1;
        setMatched(localMatched);
      } else {
        localPassed += 1;
        setPassed(localPassed);
      }
      setTick((n) => n + 1);

      window.setTimeout(() => {
        if (cancelled) return;
        setLots((prev) => {
          const rest = prev.slice(1);
          while (rest.length < 5) {
            rest.push(makeLot(id++));
          }
          return rest.map((lot, i) => (i === 0 ? { ...lot, verdict: "pending" } : lot));
        });
      }, 520);
    };

    // First inspect after glass settles, then keep cycling.
    const first = window.setTimeout(step, 700);
    const loop = window.setInterval(step, 1180);
    return () => {
      cancelled = true;
      window.clearTimeout(first);
      window.clearInterval(loop);
    };
  }, [mode]);

  const ellipsis = ".".repeat(dots);
  const headline = label || (mode === "matching" ? PHASES[phase] : "Opening Land Alerts");
  const shownDetail =
    detail ||
    (mode === "matching"
      ? "One glass over the inventory — strong fits get approved, the rest get passed."
      : "Loading your acquisition profile");

  const scanned = matched + passed;

  const active = useMemo(() => lots[0], [lots]);

  if (mode === "boot") {
    return (
      <div className="land-alerts-loader" role="status" aria-live="polite">
        <div className="land-alerts-loader-copy">
          <div className="display text-xl font-semibold land-alerts-loader-title">
            <span>{headline}</span>
            <span className="land-alerts-loader-ellipsis" aria-hidden>
              {ellipsis}
            </span>
          </div>
          <p className="mt-1 text-sm text-[var(--muted)]">{shownDetail}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="land-alerts-loader is-matching is-solo-scan" role="status" aria-live="polite">
      <div className="la-solo-stage" aria-hidden>
        <div className="la-solo-horizon" />
        <div className="la-solo-lots">
          {lots.map((lot, i) => (
            <div
              key={`${lot.id}-${lot.verdict}-${tick}-${i}`}
              className={`la-solo-lot slot-${i} is-${lot.verdict}`}
              style={{ ["--slot" as string]: String(i) }}
            >
              <div className="la-solo-lot-state">{lot.state}</div>
              <div className="la-solo-lot-acres">{lot.acres}</div>
              <div className="la-solo-lot-price">{lot.price}</div>
              {lot.verdict === "match" ? <span className="la-solo-stamp is-match">✓</span> : null}
              {lot.verdict === "pass" ? <span className="la-solo-stamp is-pass">✕</span> : null}
            </div>
          ))}
        </div>

        <div className={`la-solo-glass${active?.verdict === "match" ? " is-yes" : ""}${active?.verdict === "pass" ? " is-no" : ""}`}>
          <MagnifierIcon size={78} />
          <span className="la-solo-glass-beam" />
        </div>

        <div className="la-solo-counters">
          <span>
            <strong>{scanned}</strong> scanned
          </span>
          <span className="is-yes">
            <strong>{matched}</strong> approved
          </span>
          <span className="is-no">
            <strong>{passed}</strong> passed
          </span>
        </div>
      </div>

      <div className="land-alerts-loader-copy">
        <div className="display text-xl font-semibold land-alerts-loader-title">
          <span>{headline}</span>
          <span className="land-alerts-loader-ellipsis" aria-hidden>
            {ellipsis}
          </span>
        </div>
        <p className="mt-1 text-sm text-[var(--muted)]">{shownDetail}</p>
        <div className="land-alerts-loader-dots" aria-hidden>
          <span />
          <span />
          <span />
        </div>
      </div>
    </div>
  );
}
