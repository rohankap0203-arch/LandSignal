/** Animated magnifying glass — signals always-on land scanning. */
export function LiveMagnifier({
  className = "",
  size = 22,
  label = "Scanning live",
}: {
  className?: string;
  size?: number;
  label?: string;
}) {
  return (
    <span
      className={`live-magnifier ${className}`.trim()}
      style={{ width: size, height: size }}
      role="img"
      aria-label={label}
      title={label}
    >
      <svg viewBox="0 0 24 24" width={size} height={size} aria-hidden="true" className="live-magnifier-svg">
        <circle className="live-magnifier-lens" cx="10.5" cy="10.5" r="6.25" fill="none" stroke="currentColor" strokeWidth="2" />
        <line
          className="live-magnifier-handle"
          x1="15.2"
          y1="15.2"
          x2="20.5"
          y2="20.5"
          stroke="currentColor"
          strokeWidth="2.25"
          strokeLinecap="round"
        />
        <circle className="live-magnifier-glint" cx="8.2" cy="8.2" r="1.15" fill="currentColor" />
      </svg>
      <span className="live-magnifier-pulse" aria-hidden="true" />
    </span>
  );
}
