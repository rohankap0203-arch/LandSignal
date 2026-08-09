"use client";

/** Distinct Source vs Call actions — phone shown once, never “Call Call”. */
export function AcquireRail({
  postingUrl,
  postingLabel = "Open site",
  phone,
  office,
  findUrl,
  findLabel,
  className = "",
}: {
  postingUrl?: string | null;
  postingLabel?: string;
  phone?: string | null;
  office?: string | null;
  findUrl?: string | null;
  findLabel?: string | null;
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

  if (!postingUrl && !tel && !findUrl) return null;

  return (
    <div className={`acquire-rail ${className}`.trim()}>
      {postingUrl ? (
        <a className="acquire-block source" href={postingUrl} target="_blank" rel="noreferrer">
          <span className="acquire-kicker">Official page</span>
          <span className="acquire-value">Open {host}</span>
          <span className="acquire-hint">Sale / inventory page for this listing</span>
        </a>
      ) : (
        <div className="acquire-block source muted">
          <span className="acquire-kicker">Official page</span>
          <span className="acquire-value">No link yet</span>
        </div>
      )}

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

      {findUrl ? (
        <a className="acquire-block find" href={findUrl} target="_blank" rel="noreferrer">
          <span className="acquire-kicker">Find this parcel</span>
          <span className="acquire-value">{findLabel || "Look up the parcel ID"}</span>
        </a>
      ) : null}
    </div>
  );
}
