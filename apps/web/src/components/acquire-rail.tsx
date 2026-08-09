"use client";

import { useState } from "react";

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

/** Flip cards: front = Call / Office page; back = what to say / look for. */
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

  const [flipped, setFlipped] = useState<"call" | "web" | null>(null);

  if (!postingUrl && !tel && !findUrl) return null;

  const callScript = outreach?.call;
  const webScript = outreach?.website;

  return (
    <div className={`acquire-rail ${className}`.trim()}>
      {outreach?.one_liner ? <p className="acquire-mission">{outreach.one_liner}</p> : null}

      {/* Office / website card */}
      <div className={`acquire-flip ${flipped === "web" ? "is-flipped" : ""}`}>
        <div className="acquire-flip-inner">
          <div className="acquire-flip-face acquire-flip-front">
            {postingUrl ? (
              <a className="acquire-block source" href={postingUrl} target="_blank" rel="noreferrer">
                <span className="acquire-kicker">Office page</span>
                <span className="acquire-value">Open {host}</span>
                <span className="acquire-hint">
                  {host.includes("google.")
                    ? "Search for the live county sale / assessor page"
                    : "County / agency page for this inventory"}
                </span>
              </a>
            ) : (
              <div className="acquire-block source muted">
                <span className="acquire-kicker">Office page</span>
                <span className="acquire-value">No link yet</span>
              </div>
            )}
            {webScript ? (
              <button
                type="button"
                className="acquire-flip-btn"
                onClick={() => setFlipped("web")}
                aria-expanded={flipped === "web"}
              >
                Flip · what to look for
              </button>
            ) : null}
          </div>
          <div className="acquire-flip-face acquire-flip-back source-back">
            <div className="acquire-script">
              <div className="acquire-script-top">
                <strong>{webScript?.title || "What to look for"}</strong>
                <button type="button" className="acquire-flip-btn ghost" onClick={() => setFlipped(null)}>
                  Flip back
                </button>
              </div>
              {webScript?.opener ? <p className="acquire-script-opener">{webScript.opener}</p> : null}
              <ol className="acquire-script-list">
                {(webScript?.lines || []).slice(0, 4).map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ol>
              {(webScript?.ask_next || []).length ? (
                <>
                  <div className="acquire-script-label">Do this next</div>
                  <ul className="acquire-script-bullets">
                    {(webScript?.ask_next || []).slice(0, 3).map((line) => (
                      <li key={line}>{line}</li>
                    ))}
                  </ul>
                </>
              ) : null}
              {(webScript?.watch_outs || []).length ? (
                <>
                  <div className="acquire-script-label">Don’t miss</div>
                  <ul className="acquire-script-bullets warn">
                    {(webScript?.watch_outs || []).slice(0, 2).map((line) => (
                      <li key={line}>{line}</li>
                    ))}
                  </ul>
                </>
              ) : null}
              {postingUrl ? (
                <a className="acquire-script-cta" href={postingUrl} target="_blank" rel="noreferrer">
                  Open page with this checklist →
                </a>
              ) : null}
            </div>
          </div>
        </div>
      </div>

      {/* Call card */}
      <div className={`acquire-flip ${flipped === "call" ? "is-flipped" : ""}`}>
        <div className="acquire-flip-inner">
          <div className="acquire-flip-face acquire-flip-front">
            {tel ? (
              <a className="acquire-block call" href={tel}>
                <span className="acquire-kicker">Call the office</span>
                <span className="acquire-value">{phoneDisplay}</span>
                <span className="acquire-hint">{office || "County / agency desk"}</span>
              </a>
            ) : (
              <div className="acquire-block call muted">
                <span className="acquire-kicker">Call the office</span>
                <span className="acquire-value">No public phone listed</span>
                <span className="acquire-hint">{office || "Use the official page to contact them"}</span>
              </div>
            )}
            {callScript ? (
              <button
                type="button"
                className="acquire-flip-btn"
                onClick={() => setFlipped("call")}
                aria-expanded={flipped === "call"}
              >
                Flip · what to say
              </button>
            ) : null}
          </div>
          <div className="acquire-flip-face acquire-flip-back call-back">
            <div className="acquire-script">
              <div className="acquire-script-top">
                <strong>{callScript?.title || "What to say"}</strong>
                <button type="button" className="acquire-flip-btn ghost" onClick={() => setFlipped(null)}>
                  Flip back
                </button>
              </div>
              {callScript?.opener ? <p className="acquire-script-opener">“{callScript.opener}”</p> : null}
              <ol className="acquire-script-list">
                {(callScript?.lines || []).slice(0, 4).map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ol>
              {(callScript?.ask_next || []).length ? (
                <>
                  <div className="acquire-script-label">Ask next</div>
                  <ul className="acquire-script-bullets">
                    {(callScript?.ask_next || []).slice(0, 3).map((line) => (
                      <li key={line}>{line}</li>
                    ))}
                  </ul>
                </>
              ) : null}
              {(callScript?.watch_outs || []).length ? (
                <>
                  <div className="acquire-script-label">Watch out</div>
                  <ul className="acquire-script-bullets warn">
                    {(callScript?.watch_outs || []).slice(0, 2).map((line) => (
                      <li key={line}>{line}</li>
                    ))}
                  </ul>
                </>
              ) : null}
              {callScript?.closing ? <p className="acquire-script-close">“{callScript.closing}”</p> : null}
              {tel ? (
                <a className="acquire-script-cta call" href={tel}>
                  Dial with this script →
                </a>
              ) : null}
            </div>
          </div>
        </div>
      </div>

      {findUrl ? (
        <a className="acquire-block find" href={findUrl} target="_blank" rel="noreferrer">
          <span className="acquire-kicker">Find this parcel</span>
          <span className="acquire-value">{findLabel || "Look up the parcel ID"}</span>
        </a>
      ) : null}
    </div>
  );
}
