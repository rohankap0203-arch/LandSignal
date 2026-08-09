/** Map + pin mark matching the scout icon — stroke inherits currentColor. */
export function MapPinMark({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 96 84"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden
    >
      {/* Perspective map board (parallelogram) */}
      <path
        d="M8 46 L22 20 L86 14 L78 52 L14 58 Z"
        stroke="currentColor"
        strokeWidth="3.2"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      {/* Two vertical-ish folds */}
      <path
        d="M36 18.8 L30 54.2"
        stroke="currentColor"
        strokeWidth="2.6"
        strokeLinecap="round"
      />
      <path
        d="M58 16.6 L52 53"
        stroke="currentColor"
        strokeWidth="2.6"
        strokeLinecap="round"
      />
      {/* One horizontal fold */}
      <path
        d="M16 38.5 L80 33.2"
        stroke="currentColor"
        strokeWidth="2.6"
        strokeLinecap="round"
      />
      {/* Location pin over top-left cell */}
      <path
        d="M34 6 C27.4 6 22 11.3 22 17.8 C22 26.2 34 40 34 40 C34 40 46 26.2 46 17.8 C46 11.3 40.6 6 34 6 Z"
        stroke="currentColor"
        strokeWidth="3.2"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      <circle
        cx="34"
        cy="17.2"
        r="4.6"
        stroke="currentColor"
        strokeWidth="2.8"
      />
    </svg>
  );
}
