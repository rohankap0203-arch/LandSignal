"use client";

import { useEffect, useState } from "react";

/** Sparse magnifying-glass field — same role as LandLoader map pins, for alert matching. */
const GLASSES: { left: string; top: string; delay: string; duration: string; scale: number }[] = [
  { left: "16%", top: "58%", delay: "0s", duration: "4.1s", scale: 1 },
  { left: "38%", top: "32%", delay: "1.2s", duration: "4.5s", scale: 0.92 },
  { left: "58%", top: "62%", delay: "2.4s", duration: "4.3s", scale: 1.08 },
  { left: "74%", top: "36%", delay: "0.7s", duration: "4.7s", scale: 0.86 },
  { left: "86%", top: "54%", delay: "1.9s", duration: "4.4s", scale: 0.95 },
];

function MagnifierIcon() {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden>
      <circle cx="10.5" cy="10.5" r="6.25" fill="none" stroke="currentColor" strokeWidth="2" />
      <line
        x1="15.2"
        y1="15.2"
        x2="20.5"
        y2="20.5"
        stroke="currentColor"
        strokeWidth="2.25"
        strokeLinecap="round"
      />
    </svg>
  );
}

const PHASES = [
  "Saving your land profile",
  "Scanning live inventory",
  "Matching acres, price & states",
  "Ranking the strongest fits",
] as const;

export function LandAlertsLoader({
  label,
  detail = "Matching live inventory to your acquisition profile",
  mode = "boot",
}: {
  label?: string;
  detail?: string;
  /** boot = short page open; matching = save → results transition */
  mode?: "boot" | "matching";
}) {
  const [phase, setPhase] = useState(0);
  const [dots, setDots] = useState(1);

  useEffect(() => {
    const dotTimer = window.setInterval(() => {
      setDots((d) => (d % 3) + 1);
    }, 420);
    return () => window.clearInterval(dotTimer);
  }, []);

  useEffect(() => {
    if (mode !== "matching") return;
    const t = window.setInterval(() => {
      setPhase((p) => (p + 1) % PHASES.length);
    }, 1600);
    return () => window.clearInterval(t);
  }, [mode]);

  const ellipsis = ".".repeat(dots);
  const headline =
    label ||
    (mode === "matching" ? PHASES[phase] : "Scanning your land alerts");
  const shownDetail =
    mode === "matching"
      ? "Hang tight — we’ll open your matches as soon as scoring finishes."
      : detail;

  return (
    <div
      className={`land-alerts-loader${mode === "matching" ? " is-matching" : ""}`}
      role="status"
      aria-live="polite"
    >
      <div className="land-alerts-loader-stage" aria-hidden>
        <svg className="land-alerts-loader-svg" viewBox="0 0 360 160" preserveAspectRatio="none">
          <defs>
            <linearGradient id="alertLandGrad" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stopColor="rgba(31,107,79,0.5)" />
              <stop offset="55%" stopColor="rgba(15,61,46,0.32)" />
              <stop offset="100%" stopColor="rgba(196,92,38,0.3)" />
            </linearGradient>
          </defs>
          <rect width="360" height="160" fill="url(#alertLandGrad)" />
          {[42, 58, 74, 90, 106, 122].map((y, i) => (
            <path
              key={y}
              className="land-contour"
              style={{ animationDelay: `${i * 0.18}s` }}
              d={`M0 ${y} C 60 ${y - 14}, 120 ${y + 12}, 180 ${y - 6} S 300 ${y + 10}, 360 ${y - 4}`}
              fill="none"
              stroke="rgba(255,255,255,0.28)"
              strokeWidth="1.4"
            />
          ))}
        </svg>
        <div className="land-alerts-glass-field">
          {GLASSES.map((g, i) => (
            <span
              key={i}
              className="land-alerts-scout-glass"
              style={{
                left: g.left,
                top: g.top,
                animationDelay: g.delay,
                animationDuration: g.duration,
                ["--glass-scale" as string]: String(g.scale),
              }}
            >
              <MagnifierIcon />
            </span>
          ))}
        </div>
        <div className="land-alerts-scan" />
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
