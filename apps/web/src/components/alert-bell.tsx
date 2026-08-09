/** Bell icon for Land Alerts — static in the CTA, animated on the alerts page. */
export function AlertBell({
  className = "",
  size = 18,
  label = "Land Alerts",
  animated = false,
}: {
  className?: string;
  size?: number;
  label?: string;
  animated?: boolean;
}) {
  return (
    <span
      className={`alert-bell${animated ? " is-live" : ""} ${className}`.trim()}
      style={{ width: size, height: size }}
      role="img"
      aria-label={label}
      title={label}
    >
      <svg viewBox="0 0 24 24" width={size} height={size} aria-hidden="true" className="alert-bell-svg">
        <path
          d="M12 3.2c-2.6 0-4.7 2-4.7 4.5v2.1c0 .9-.3 1.8-.9 2.5l-1.1 1.3c-.7.8-.2 2.1.9 2.1h12.6c1.1 0 1.6-1.3.9-2.1l-1.1-1.3c-.6-.7-.9-1.6-.9-2.5V7.7c0-2.5-2.1-4.5-4.7-4.5Z"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.9"
          strokeLinejoin="round"
        />
        <path
          d="M10 18.6a2.1 2.1 0 0 0 4 0"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.9"
          strokeLinecap="round"
        />
      </svg>
      {animated ? <span className="alert-bell-ring" aria-hidden="true" /> : null}
    </span>
  );
}
