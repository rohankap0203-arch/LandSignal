"use client";

import { useEffect, useMemo, useRef, useState } from "react";

type ScriptSide = {
  title?: string;
  subtitle?: string;
  opener?: string;
  lines?: string[];
  ask_next?: string[];
  watch_outs?: string[];
  closing?: string;
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
};

function buildGuideSteps(kind: "web" | "call", script: ScriptSide | undefined): Step[] {
  if (!script) return [];
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

function GuideDropdown({
  open,
  tone,
  steps,
  onClose,
}: {
  open: boolean;
  tone: "source" | "call";
  steps: Step[];
  onClose: () => void;
}) {
  const [i, setI] = useState(0);
  const panelRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (open) setI(0);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    const onDoc = (e: MouseEvent) => {
      if (!panelRef.current) return;
      if (!panelRef.current.contains(e.target as Node)) onClose();
    };
    window.addEventListener("keydown", onKey);
    // defer so the opening click doesn’t instantly close
    const t = window.setTimeout(() => document.addEventListener("mousedown", onDoc), 0);
    return () => {
      window.clearTimeout(t);
      window.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onDoc);
    };
  }, [open, onClose]);

  if (!open || !steps.length) return null;
  const step = steps[Math.min(i, steps.length - 1)];
  const n = steps.length;

  return (
    <div ref={panelRef} className={`acquire-guide tone-${tone}`} role="dialog" aria-label="Guide steps">
      <div className="acquire-guide-head">
        <span className="acquire-kicker">{step.kicker}</span>
        <span className="acquire-step-count">
          {i + 1}/{n}
        </span>
      </div>
      <p className="acquire-guide-body">{step.body}</p>
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
  steps,
  open,
  onToggle,
}: {
  tone: "source" | "call";
  kicker: string;
  value: string;
  hint?: string | null;
  href?: string | null;
  steps: Step[];
  open: boolean;
  onToggle: () => void;
}) {
  const hasGuide = steps.length > 0;
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
        <>
          <button
            type="button"
            className={`acquire-chevron ${open ? "on" : ""}`}
            aria-label={open ? "Hide guide" : "Show guide steps"}
            aria-expanded={open}
            onClick={onToggle}
          >
            <span aria-hidden>v</span>
          </button>
          <GuideDropdown
            open={open}
            tone={tone}
            steps={steps}
            onClose={() => {
              if (open) onToggle();
            }}
          />
        </>
      ) : null}
    </div>
  );
}

/** Compact Call / Office cards; centered v opens a step-toggle dropdown. */
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

  if (!postingUrl && !tel && !findUrl) return null;

  return (
    <div className={`acquire-rail ${className}`.trim()}>
      {outreach?.one_liner ? <p className="acquire-mission">{outreach.one_liner}</p> : null}

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
        steps={webSteps}
        open={openGuide === "web"}
        onToggle={() => setOpenGuide((v) => (v === "web" ? null : "web"))}
      />

      <ActionCard
        tone="call"
        kicker="Call the office"
        value={phoneDisplay || "No public phone listed"}
        hint={office || (tel ? "County / agency desk" : "Use the official page to contact them")}
        href={tel}
        steps={callSteps}
        open={openGuide === "call"}
        onToggle={() => setOpenGuide((v) => (v === "call" ? null : "call"))}
      />

      {findUrl ? (
        <a className="acquire-block find" href={findUrl} target="_blank" rel="noreferrer">
          <span className="acquire-kicker">Find this parcel</span>
          <span className="acquire-value">{findLabel || "Look up the parcel ID"}</span>
        </a>
      ) : null}
    </div>
  );
}
