"use client";

import { useEffect, useState } from "react";

type Props = {
  question: string;
  aftertaste?: string | null;
  /** ms per character while typing */
  charMs?: number;
  /** hold fully typed text before restarting */
  holdMs?: number;
};

export function AskYourselfTypewriter({
  question,
  aftertaste,
  charMs = 28,
  holdMs = 7000,
}: Props) {
  const fullQuestion = question.trim();
  const fullAfter = (aftertaste || "").trim();
  const [qLen, setQLen] = useState(0);
  const [aLen, setALen] = useState(0);
  const [phase, setPhase] = useState<"question" | "aftertaste" | "hold">("question");
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
  }, [fullQuestion, fullAfter]);

  useEffect(() => {
    if (reducedMotion) {
      setQLen(fullQuestion.length);
      setALen(fullAfter.length);
      setPhase("hold");
      return;
    }

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
  }, [phase, qLen, aLen, fullQuestion, fullAfter, charMs, holdMs, reducedMotion]);

  const qShown = fullQuestion.slice(0, qLen);
  const aShown = fullAfter.slice(0, aLen);
  const typing = phase === "question" || phase === "aftertaste";

  return (
    <div className="ask-yourself-typewriter" aria-live="polite">
      <p className="ask-yourself-q display mt-3 text-2xl font-semibold leading-snug md:text-[1.85rem]">
        <span className="sr-only">{fullQuestion}</span>
        <span aria-hidden="true">
          {qShown}
          {phase === "question" && typing ? <span className="ask-caret" /> : null}
        </span>
      </p>
      {fullAfter ? (
        <p className="mt-4 text-sm text-[var(--muted)]">
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
