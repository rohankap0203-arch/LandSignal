"use client";

import { useEffect, useState } from "react";

type Props = {
  label?: string;
  question: string;
  /** "Because…" reality line that follows the question */
  because?: string | null;
  aftertaste?: string | null;
  /** ms per character while typing */
  charMs?: number;
  /** hold fully typed text before restarting */
  holdMs?: number;
};

export function AskYourselfTypewriter({
  label = "Ask yourself",
  question,
  because,
  aftertaste,
  charMs = 28,
  holdMs = 10000,
}: Props) {
  const fullQuestion = question.trim();
  const fullAfter = (because || aftertaste || "").trim();
  const [qLen, setQLen] = useState(0);
  const [aLen, setALen] = useState(0);
  const [phase, setPhase] = useState<"question" | "aftertaste" | "hold">("question");
  const [paused, setPaused] = useState(false);
  const [reducedMotion, setReducedMotion] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const apply = () => setReducedMotion(mq.matches);
    apply();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, []);

  useEffect(() => {
    setQLen(0);
    setALen(0);
    setPhase("question");
    setPaused(false);
  }, [fullQuestion, fullAfter]);

  useEffect(() => {
    if (reducedMotion) {
      setQLen(fullQuestion.length);
      setALen(fullAfter.length);
      setPhase("hold");
      return;
    }

    if (paused) return;

    if (phase === "question") {
      if (qLen >= fullQuestion.length) {
        setPhase(fullAfter ? "aftertaste" : "hold");
        return;
      }
      const t = window.setTimeout(() => setQLen((n) => n + 1), charMs);
      return () => window.clearTimeout(t);
    }

    if (phase === "aftertaste") {
      if (aLen >= fullAfter.length) {
        setPhase("hold");
        return;
      }
      const t = window.setTimeout(() => setALen((n) => n + 1), Math.max(18, charMs - 6));
      return () => window.clearTimeout(t);
    }

    // hold, then restart
    const t = window.setTimeout(() => {
      setQLen(0);
      setALen(0);
      setPhase("question");
    }, holdMs);
    return () => window.clearTimeout(t);
  }, [phase, qLen, aLen, fullQuestion, fullAfter, charMs, holdMs, reducedMotion, paused]);

  const qShown = fullQuestion.slice(0, qLen);
  const aShown = fullAfter.slice(0, aLen);
  const typing = !paused && (phase === "question" || phase === "aftertaste");

  return (
    <div className="ask-yourself-typewriter" aria-live="polite">
      <div className="ask-yourself-head">
        <div className="text-[10px] uppercase tracking-[0.16em] text-[var(--muted)]">{label}</div>
        {!reducedMotion ? (
          <button
            type="button"
            className="ask-pause-btn"
            aria-pressed={paused}
            aria-label={paused ? "Play typewriter" : "Pause typewriter"}
            title={paused ? "Play" : "Pause"}
            onClick={() => setPaused((p) => !p)}
          >
            {paused ? (
              <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true">
                <path fill="currentColor" d="M8 5v14l11-7L8 5z" />
              </svg>
            ) : (
              <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true">
                <path fill="currentColor" d="M7 5h3v14H7V5zm7 0h3v14h-3V5z" />
              </svg>
            )}
          </button>
        ) : null}
      </div>
      <p className="ask-yourself-q display mt-3 text-2xl font-semibold leading-snug md:text-[1.85rem]">
        <span className="sr-only">{fullQuestion}</span>
        <span aria-hidden="true">
          {qShown}
          {phase === "question" && typing ? <span className="ask-caret" /> : null}
        </span>
      </p>
      {fullAfter ? (
        <p className="ask-yourself-because mt-4 text-sm leading-relaxed text-[var(--muted)]">
          <span className="sr-only">{fullAfter}</span>
          <span aria-hidden="true">
            {aShown}
            {phase === "aftertaste" && typing ? <span className="ask-caret muted" /> : null}
          </span>
        </p>
      ) : null}
    </div>
  );
}
