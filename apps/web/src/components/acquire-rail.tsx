"use client";

import { useMemo, useState } from "react";

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
  href?: string | null;
  hrefLabel?: string;
};

function buildSteps(
  kind: "web" | "call",
  script: ScriptSide | undefined,
  action: Step,
): Step[] {
  const steps: Step[] = [action];
  if (!script) return steps;
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
    steps.push({
      kicker: "Watch out",
      body: line,
    });
  }
  if (script.closing && kind === "call") {
    steps.push({
      kicker: "Close with",
      body: script.closing,
    });
  }
  return steps;
}

function AcquireStepper({
  tone,
  steps,
  emptyHint,
}: {
  tone: "source" | "call";
  steps: Step[];
  emptyHint?: string;
}) {
  const [i, setI] = useState(0);
  const step = steps[Math.min(i, Math.max(0, steps.length - 1))] || null;
  const n = steps.length;
  const atAction = i === 0;

  if (!step) {
    return (
      <div className={`acquire-stepper tone-${tone} muted`}>
        <p className="acquire-step-body">{emptyHint || "Nothing here yet"}</p>
      </div>
    );
  }

  return (
    <div className={`acquire-stepper tone-${tone}`}>
      <div className="acquire-step-head">
        <span className="acquire-kicker">{step.kicker}</span>
        {n > 1 ? (
          <span className="acquire-step-count">
            {i + 1}/{n}
          </span>
        ) : null}
      </div>

      {atAction && step.href ? (
        <a className="acquire-step-action" href={step.href} target={step.href.startsWith("tel:") ? undefined : "_blank"} rel="noreferrer">
          <span className="acquire-value">{step.body}</span>
          {step.hrefLabel ? <span className="acquire-hint">{step.hrefLabel}</span> : null}
        </a>
      ) : (
        <p className={`acquire-step-body ${atAction ? "action" : ""}`}>{step.body}</p>
      )}

      {n > 1 ? (
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
      ) : null}
    </div>
  );
}

/** Office page + Call as left→right step guides; Find parcel stays clear below. */
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

  const webSteps = useMemo(
    () =>
      buildSteps(
        "web",
        outreach?.website,
        postingUrl
          ? {
              kicker: "Office page",
              body: `Open ${host}`,
              href: postingUrl,
              hrefLabel: host.includes("google.")
                ? "Search for the live county sale / assessor page"
                : "County / agency page for this inventory",
            }
          : {
              kicker: "Office page",
              body: "No link yet",
              hrefLabel: "Use parcel lookup below if you have it",
            },
      ),
    [outreach?.website, postingUrl, host],
  );

  const callSteps = useMemo(
    () =>
      buildSteps(
        "call",
        outreach?.call,
        tel
          ? {
              kicker: "Call the office",
              body: phoneDisplay || "Call",
              href: tel,
              hrefLabel: office || "County / agency desk",
            }
          : {
              kicker: "Call the office",
              body: "No public phone listed",
              hrefLabel: office || "Use the official page to contact them",
            },
      ),
    [outreach?.call, tel, phoneDisplay, office],
  );

  if (!postingUrl && !tel && !findUrl) return null;

  return (
    <div className={`acquire-rail ${className}`.trim()}>
      {outreach?.one_liner ? <p className="acquire-mission">{outreach.one_liner}</p> : null}

      <AcquireStepper tone="source" steps={webSteps} emptyHint="No office page yet" />
      <AcquireStepper tone="call" steps={callSteps} emptyHint="No phone listed" />

      {findUrl ? (
        <a className="acquire-block find" href={findUrl} target="_blank" rel="noreferrer">
          <span className="acquire-kicker">Find this parcel</span>
          <span className="acquire-value">{findLabel || "Look up the parcel ID"}</span>
        </a>
      ) : null}
    </div>
  );
}
