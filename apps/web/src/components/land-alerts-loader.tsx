/** Brief Land Alerts boot visual — radar sweep + live glass, distinct from search LandLoader. */
export function LandAlertsLoader({
  label = "Scanning your land alerts…",
  detail = "Matching live inventory to your acquisition profile",
}: {
  label?: string;
  detail?: string;
}) {
  return (
    <div className="land-alerts-loader" role="status" aria-live="polite">
      <div className="land-alerts-loader-stage" aria-hidden>
        <div className="land-alerts-loader-radar">
          <span className="land-alerts-loader-ring r1" />
          <span className="land-alerts-loader-ring r2" />
          <span className="land-alerts-loader-ring r3" />
          <span className="land-alerts-loader-sweep" />
          <span className="land-alerts-loader-blip b1" />
          <span className="land-alerts-loader-blip b2" />
          <span className="land-alerts-loader-blip b3" />
          <span className="land-alerts-loader-blip b4" />
          <span className="land-alerts-loader-glass">
            <svg viewBox="0 0 24 24" width="28" height="28" aria-hidden="true">
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
          </span>
        </div>
      </div>
      <div className="land-alerts-loader-copy">
        <div className="display text-xl font-semibold">{label}</div>
        <p className="mt-1 text-sm text-[var(--muted)]">{detail}</p>
        <div className="land-alerts-loader-bar" aria-hidden>
          <span />
        </div>
      </div>
    </div>
  );
}
