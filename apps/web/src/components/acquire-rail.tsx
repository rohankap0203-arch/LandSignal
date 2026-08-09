"use client";

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

type ScriptStep = {
  kicker?: string;
  body?: string;
  fulfills?: string;
};

type ScriptSide = {
  title?: string;
  subtitle?: string;
  opener?: string;
  lines?: string[];
  ask_next?: string[];
  watch_outs?: string[];
  closing?: string;
  steps?: ScriptStep[];
};

export type OutreachPlaybook = {
  office?: string;
  place?: string;
  parcel_ref?: string;
  channel?: string;
  one_liner?: string;
  call?: ScriptSide;
  website?: ScriptSide;
};

type Step = {
  kicker: string;
  body: string;
  fulfills?: string;
};

function buildGuideSteps(kind: "web" | "call", script: ScriptSide | undefined): Step[] {
  if (!script) return [];
  if (script.steps?.length) {
    return script.steps
      .filter((s) => s.body)
      .map((s) => ({
        kicker: s.kicker || (kind === "call" ? "Say" : "Look"),
        body: String(s.body),
        fulfills: s.fulfills ? String(s.fulfills) : undefined,
      }));
  }
  // Legacy flat shape
  const steps: Step[] = [];
  if (script.opener) {
    steps.push({
      kicker: kind === "call" ? "Say this first" : "Start here",
      body: script.opener,
    });
  }
  for (const line of (script.lines || []).slice(0, 3)) {
    steps.push({
      kicker: kind === "call" ? "Then say" : "Look for",
      body: line,
    });
  }
  for (const line of (script.ask_next || []).slice(0, 2)) {
    steps.push({
      kicker: kind === "call" ? "Ask next" : "Do next",
      body: line,
    });
  }
  for (const line of (script.watch_outs || []).slice(0, 1)) {
    steps.push({ kicker: "Watch out", body: line });
  }
  if (script.closing && kind === "call") {
    steps.push({ kicker: "Close with", body: script.closing });
  }
  return steps;
}

function quoteIfNeeded(text: string): string {
  const t = text.trim().replace(/^["“”']+|["“”']+$/g, "");
  return `“${t}”`;
}

function formatStepBody(tone: "source" | "call", step: Step): string {
  if (tone !== "call") return step.body;
  if (step.kicker === "Watch out") return step.body;
  return quoteIfNeeded(step.body);
}

/** Fallback if API didn’t send fulfills — keep the step useful. */
function fallbackFulfills(tone: "source" | "call", step: Step): string {
  if (step.fulfills?.trim()) return step.fulfills.trim();
  const k = step.kicker.toLowerCase();
  if (tone === "call") {
    if (k.includes("first")) return "Why this opener: they hear a real buyer on this exact file, not a general info call.";
    if (k.includes("ask")) return "Why ask: a yes/no here changes whether you keep spending time on this pin.";
    if (k.includes("watch")) return "Why it matters: flags the local trap before it eats this deal.";
    if (k.includes("close")) return "Why close this way: leaves a clean reason to call back with facts.";
    return "Why say this: advances status, price, or who can sell this exact pin.";
  }
  if (k.includes("start")) return "Why first: live status decides if this pin is obtainable at all.";
  if (k.includes("do next")) return "Why next: turns the page dig into facts for What to say.";
  if (k.includes("watch")) return "Why it matters: stops a dead-end dig on a pin that isn’t buyable.";
  return "Why this check: pulls the fact you need before you dial or bid.";
}

/** Compact animated reveal — clearer than a bare V for “open the guide”. */
function GuideRevealMark({ open }: { open: boolean }) {
  return (
    <span className={`acquire-reveal-mark ${open ? "on" : ""}`} aria-hidden>
      <span className="acquire-reveal-bar" />
      <span className="acquire-reveal-bar" />
      <span className="acquire-reveal-bar" />
    </span>
  );
}

function GuidePanel({
  tone,
  steps,
}: {
  tone: "source" | "call";
  steps: Step[];
}) {
  const [i, setI] = useState(0);
  const measureRef = useRef<HTMLDivElement | null>(null);
  const [bodyMin, setBodyMin] = useState<number>(0);

  useEffect(() => {
    setI(0);
  }, [steps]);

  // Lock block height to the tallest step (body + fulfills) so ← → never jumps
  useLayoutEffect(() => {
    const root = measureRef.current;
    if (!root || !steps.length) {
      setBodyMin(0);
      return;
    }
    let max = 0;
    const nodes = root.querySelectorAll<HTMLElement>("[data-step-measure]");
    nodes.forEach((el) => {
      max = Math.max(max, el.offsetHeight);
    });
    setBodyMin(max);
  }, [steps]);

  if (!steps.length) return null;
  const step = steps[Math.min(i, steps.length - 1)];
  const n = steps.length;
  const bodies = steps.map((s) => formatStepBody(tone, s));
  const whys = steps.map((s) => fallbackFulfills(tone, s));
  const body = bodies[Math.min(i, bodies.length - 1)];
  const why = whys[Math.min(i, whys.length - 1)];

  return (
    <div className={`acquire-guide tone-${tone}`} role="region" aria-label="Guide steps">
      <div className="acquire-guide-head">
        <span className="acquire-kicker">{step.kicker}</span>
        <span className="acquire-step-count">
          {i + 1}/{n}
        </span>
      </div>
      <div className="acquire-guide-body-wrap" style={bodyMin ? { minHeight: bodyMin } : undefined}>
        <div className="acquire-guide-step">
          <p className="acquire-guide-body">{body}</p>
          <p className="acquire-guide-why">
            <span className="acquire-guide-why-k">Why · </span>
            {why}
          </p>
        </div>
      </div>
      <div className="acquire-guide-measure" ref={measureRef} aria-hidden>
        {steps.map((s, idx) => (
          <div key={idx} data-step-measure className="acquire-guide-step">
            <p className="acquire-guide-body">{bodies[idx]}</p>
            <p className="acquire-guide-why">
              <span className="acquire-guide-why-k">Why · </span>
              {whys[idx]}
            </p>
          </div>
        ))}
      </div>
      <div className="acquire-step-nav">
        <button
          type="button"
          className="acquire-step-btn"
          aria-label="Previous step"
          disabled={i <= 0}
          onClick={() => setI((v) => Math.max(0, v - 1))}
        >
          ←
        </button>
        <div className="acquire-step-dots" aria-hidden>
          {steps.map((_, di) => (
            <span key={di} className={`acquire-step-dot ${di === i ? "on" : ""}`} />
          ))}
        </div>
        <button
          type="button"
          className="acquire-step-btn"
          aria-label="Next step"
          disabled={i >= n - 1}
          onClick={() => setI((v) => Math.min(n - 1, v + 1))}
        >
          →
        </button>
      </div>
    </div>
  );
}

function ActionCard({
  tone,
  kicker,
  value,
  hint,
  href,
  stepCount,
  open,
  onToggle,
}: {
  tone: "source" | "call";
  kicker: string;
  value: string;
  hint?: string | null;
  href?: string | null;
  stepCount: number;
  open: boolean;
  onToggle: () => void;
}) {
  const hasGuide = stepCount > 0;
  const revealLabel = tone === "call" ? "What to say" : "Look-for";
  return (
    <div className={`acquire-card tone-${tone} ${open ? "open" : ""}`}>
      {href ? (
        <a
          className={`acquire-block ${tone}`}
          href={href}
          target={href.startsWith("tel:") ? undefined : "_blank"}
          rel="noreferrer"
        >
          <span className="acquire-kicker">{kicker}</span>
          <span className="acquire-value">{value}</span>
          {hint ? <span className="acquire-hint">{hint}</span> : null}
        </a>
      ) : (
        <div className={`acquire-block ${tone} muted`}>
          <span className="acquire-kicker">{kicker}</span>
          <span className="acquire-value">{value}</span>
          {hint ? <span className="acquire-hint">{hint}</span> : null}
        </div>
      )}
      {hasGuide ? (
        <button
          type="button"
          className={`acquire-reveal ${open ? "on" : ""}`}
          aria-label={open ? `Hide ${revealLabel}` : `Show ${revealLabel}`}
          aria-expanded={open}
          onClick={onToggle}
        >
          <GuideRevealMark open={open} />
          <span className="acquire-reveal-label">{open ? "Hide" : revealLabel}</span>
          <span className="acquire-reveal-count">{stepCount}</span>
        </button>
      ) : null}
    </div>
  );
}

/** Equal-height Call / Office cards; animated reveal expands a full-width step guide. */
export function AcquireRail({
  postingUrl,
  postingLabel = "Open site",
  phone,
  office,
  findUrl,
  findLabel,
  outreach,
  className = "",
}: {
  postingUrl?: string | null;
  postingLabel?: string;
  phone?: string | null;
  office?: string | null;
  findUrl?: string | null;
  findLabel?: string | null;
  outreach?: OutreachPlaybook | null;
  className?: string;
}) {
  const phoneDisplay = (phone || "").replace(/^Call\s+/i, "").trim() || null;
  const tel = phoneDisplay ? `tel:${phoneDisplay.replace(/[^\d+]/g, "")}` : null;
  const host = (() => {
    if (!postingUrl) return postingLabel;
    try {
      return new URL(postingUrl).hostname.replace(/^www\./, "");
    } catch {
      return postingLabel;
    }
  })();

  const webSteps = useMemo(() => buildGuideSteps("web", outreach?.website), [outreach?.website]);
  const callSteps = useMemo(() => buildGuideSteps("call", outreach?.call), [outreach?.call]);
  const [openGuide, setOpenGuide] = useState<"web" | "call" | null>(null);
  const activeSteps = openGuide === "web" ? webSteps : openGuide === "call" ? callSteps : [];
  const activeTone = openGuide === "call" ? "call" : "source";

  if (!postingUrl && !tel && !findUrl) return null;

  return (
    <div className={`acquire-rail ${className}`.trim()}>
      {outreach?.one_liner ? <p className="acquire-mission">{outreach.one_liner}</p> : null}

      <div className="acquire-card-row">
        <ActionCard
          tone="source"
          kicker="Office page"
          value={postingUrl ? `Open ${host}` : "No link yet"}
          hint={
            postingUrl
              ? host.includes("google.")
                ? "Search for the live county sale / assessor page"
                : "County / agency page for this inventory"
              : "Use parcel lookup below if you have it"
          }
          href={postingUrl}
          stepCount={webSteps.length}
          open={openGuide === "web"}
          onToggle={() => setOpenGuide((v) => (v === "web" ? null : "web"))}
        />

        <ActionCard
          tone="call"
          kicker="Call the office"
          value={phoneDisplay || "No public phone listed"}
          hint={office || (tel ? "County / agency desk" : "Use the official page to contact them")}
          href={tel}
          stepCount={callSteps.length}
          open={openGuide === "call"}
          onToggle={() => setOpenGuide((v) => (v === "call" ? null : "call"))}
        />
      </div>

      {openGuide && activeSteps.length > 0 ? (
        <GuidePanel key={openGuide} tone={activeTone} steps={activeSteps} />
      ) : null}

      {findUrl ? (
        <a className="acquire-block find" href={findUrl} target="_blank" rel="noreferrer">
          <span className="acquire-kicker">Find this parcel</span>
          <span className="acquire-value">{findLabel || "Look up the parcel ID"}</span>
        </a>
      ) : null}
    </div>
  );
}
