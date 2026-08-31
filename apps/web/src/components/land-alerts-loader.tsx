"use client";

import { useEffect, useMemo, useState } from "react";

type LotVerdict = "pending" | "match" | "pass";

type LotCard = {
  id: number;
  state: string;
  acres: string;
  price: string;
  idLabel: string;
  verdict: LotVerdict;
};

const STATES = ["FL", "TX", "GA", "NC", "AZ", "CO", "OR", "TN", "VA", "OK", "NM", "MT"];
const ACRES = ["4.2 ac", "12 ac", "28 ac", "5.5 ac", "41 ac", "9 ac", "18 ac", "63 ac", "3.1 ac", "22 ac"];
const PRICES = ["$48k", "$120k", "$86k", "$210k", "$64k", "$175k", "$95k", "$310k", "$39k", "$142k"];

function MagnifierIcon({ size = 64 }: { size?: number }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} aria-hidden className="la-solo-glass-svg">
      <circle cx="10.5" cy="10.5" r="6.25" fill="rgba(255,255,255,0.08)" stroke="currentColor" strokeWidth="1.85" />
      <circle cx="10.5" cy="10.5" r="3.4" fill="none" stroke="currentColor" strokeWidth="1.1" opacity="0.4" />
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
    idLabel: `LOT-${String(1000 + (id % 9000)).padStart(4, "0")}`,
    verdict,
  };
}

const PHASES = [
  "Querying live inventory",
  "Evaluating parcel filters",
  "Scoring preference fit",
  "Building match set",
] as const;

/** Solo magnifying-glass scan — inspects lots, keeps fits, dismisses the rest. */
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
  const [lots, setLots] = useState<LotCard[]>(() => [0, 1, 2, 3, 4].map((i) => makeLot(i)));

  useEffect(() => {
    const t = window.setInterval(() => setDots((d) => (d % 3) + 1), 380);
    return () => window.clearInterval(t);
  }, []);

  useEffect(() => {
    if (mode !== "matching") return;
    const t = window.setInterval(() => setPhase((p) => (p + 1) % PHASES.length), 1500);
    return () => window.clearInterval(t);
  }, [mode]);

  useEffect(() => {
    if (mode !== "matching") return;
    let cancelled = false;
    let id = 5;

    const step = () => {
      if (cancelled) return;
      const keep = Math.random() < 0.42;
      setLots((prev) =>
        prev.map((lot, i) => {
          if (i !== 0 || lot.verdict !== "pending") return lot;
          return { ...lot, verdict: keep ? "match" : "pass" };
        }),
      );
      setTick((n) => n + 1);

      window.setTimeout(() => {
        if (cancelled) return;
        setLots((prev) => {
          const rest = prev.slice(1);
          while (rest.length < 5) rest.push(makeLot(id++));
          return rest.map((lot, i) => (i === 0 ? { ...lot, verdict: "pending" } : lot));
        });
      }, 520);
    };

    const first = window.setTimeout(step, 700);
    const loop = window.setInterval(step, 1180);
    return () => {
      cancelled = true;
      window.clearTimeout(first);
      window.clearInterval(loop);
    };
  }, [mode]);

  const ellipsis = ".".repeat(dots);
  const headline = label || (mode === "matching" ? PHASES[phase] : "Land Alerts");
  const shownDetail =
    detail ||
    (mode === "matching"
      ? "Running your acquisition filters against live public parcels."
      : "Preparing your profile");

  const active = useMemo(() => lots[0], [lots]);
  const statusWord =
    active?.verdict === "match" ? "KEEP" : active?.verdict === "pass" ? "SKIP" : "SCAN";

  if (mode === "boot") {
    return null;
  }

  return (
    <div className="land-alerts-loader is-matching is-solo-scan" role="status" aria-live="polite">
      <div className="la-solo-stage" aria-hidden>
        <div className="la-solo-horizon" />
        <div className="la-solo-hud">
          <span className="la-solo-hud-chip">FILTER PASS</span>
          <span className={`la-solo-hud-status is-${active?.verdict || "pending"}`}>{statusWord}</span>
        </div>
        <div className="la-solo-lots">
          {lots.map((lot, i) => (
            <div
              key={`${lot.id}-${lot.verdict}-${tick}-${i}`}
              className={`la-solo-lot slot-${i} is-${lot.verdict}`}
              style={{ ["--slot" as string]: String(i) }}
            >
              <div className="la-solo-lot-id">{lot.idLabel}</div>
              <div className="la-solo-lot-state">{lot.state}</div>
              <div className="la-solo-lot-acres">{lot.acres}</div>
              <div className="la-solo-lot-price">{lot.price}</div>
              {lot.verdict === "match" ? <span className="la-solo-stamp is-match">KEEP</span> : null}
              {lot.verdict === "pass" ? <span className="la-solo-stamp is-pass">SKIP</span> : null}
            </div>
          ))}
        </div>

        <div
          className={`la-solo-glass${active?.verdict === "match" ? " is-yes" : ""}${
            active?.verdict === "pass" ? " is-no" : ""
          }`}
        >
          <MagnifierIcon size={78} />
          <span className="la-solo-glass-beam" />
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
