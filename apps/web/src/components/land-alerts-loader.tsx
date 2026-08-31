"use client";

import { useEffect, useRef, useState } from "react";

type LotVerdict = "pending" | "match" | "pass";

type LotCard = {
  id: number;
  state: string;
  acres: string;
  price: string;
  idLabel: string;
};

type ExitLot = LotCard & { verdict: "match" | "pass" };

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

function makeLot(id: number): LotCard {
  return {
    id,
    state: STATES[id % STATES.length],
    acres: ACRES[id % ACRES.length],
    price: PRICES[id % PRICES.length],
    idLabel: `LOT-${String(1000 + (id % 9000)).padStart(4, "0")}`,
  };
}

function LotFace({ lot }: { lot: LotCard }) {
  return (
    <>
      <div className="la-solo-lot-id">{lot.idLabel}</div>
      <div className="la-solo-lot-state">{lot.state}</div>
      <div className="la-solo-lot-acres">{lot.acres}</div>
      <div className="la-solo-lot-price">{lot.price}</div>
    </>
  );
}

const PHASES = [
  "Querying live inventory",
  "Evaluating parcel filters",
  "Scoring preference fit",
  "Building match set",
] as const;

const QUEUE_LEN = 3;
const STEP_MS = 1100;
const EXIT_MS = 560;

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
  const [phase, setPhase] = useState(0);
  const [queue, setQueue] = useState<LotCard[]>(() =>
    Array.from({ length: QUEUE_LEN }, (_, i) => makeLot(i)),
  );
  const [exitLot, setExitLot] = useState<ExitLot | null>(null);
  const [glassMood, setGlassMood] = useState<LotVerdict>("pending");
  const nextId = useRef(QUEUE_LEN);
  const queueRef = useRef(queue);
  const busy = useRef(false);
  queueRef.current = queue;

  useEffect(() => {
    if (mode !== "matching") return;
    const t = window.setInterval(() => setPhase((p) => (p + 1) % PHASES.length), 1800);
    return () => window.clearInterval(t);
  }, [mode]);

  useEffect(() => {
    if (mode !== "matching") return;
    let cancelled = false;
    let timer = 0;

    const step = () => {
      if (cancelled || busy.current) return;
      const [front, ...rest] = queueRef.current;
      if (!front) return;
      busy.current = true;

      const keep = Math.random() < 0.42;
      const verdict: "match" | "pass" = keep ? "match" : "pass";
      const refill = [...rest];
      while (refill.length < QUEUE_LEN) {
        refill.push(makeLot(nextId.current++));
      }

      setExitLot({ ...front, verdict });
      setGlassMood(verdict);
      setQueue(refill);
      queueRef.current = refill;

      window.setTimeout(() => {
        if (cancelled) return;
        setExitLot(null);
        setGlassMood("pending");
        busy.current = false;
      }, EXIT_MS);
    };

    const first = window.setTimeout(step, 480);
    timer = window.setInterval(step, STEP_MS);
    return () => {
      cancelled = true;
      window.clearTimeout(first);
      window.clearInterval(timer);
    };
  }, [mode]);

  const headline = label || (mode === "matching" ? PHASES[phase] : "Land Alerts");
  const shownDetail =
    detail ||
    (mode === "matching"
      ? "Running your acquisition filters against live public parcels."
      : "Preparing your profile");

  if (mode === "boot") {
    return null;
  }

  return (
    <div className="land-alerts-loader is-matching is-solo-scan" role="status" aria-live="polite">
      <div className="la-solo-stage" aria-hidden>
        <div className="la-solo-horizon" />

        <div className="la-solo-lots">
          {queue.map((lot, i) => (
            <div
              key={lot.id}
              className={`la-solo-lot slot-${i} is-pending`}
              style={{ ["--slot" as string]: String(i) }}
            >
              <LotFace lot={lot} />
            </div>
          ))}
          {exitLot ? (
            <div key={`exit-${exitLot.id}`} className={`la-solo-lot is-exit is-${exitLot.verdict}`}>
              <LotFace lot={exitLot} />
              <span className={`la-solo-stamp is-${exitLot.verdict}`}>
                {exitLot.verdict === "match" ? "KEEP" : "SKIP"}
              </span>
            </div>
          ) : null}
        </div>

        <div
          className={`la-solo-glass${glassMood === "match" ? " is-yes" : ""}${
            glassMood === "pass" ? " is-no" : ""
          }`}
        >
          <MagnifierIcon size={64} />
          <span className="la-solo-glass-beam" />
        </div>
      </div>

      <div className="land-alerts-loader-copy">
        <div className="display text-xl font-semibold land-alerts-loader-title">
          <span>{headline}</span>
          <span className="land-alerts-loader-ellipsis" aria-hidden />
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
