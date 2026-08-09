"use client";

import { useId } from "react";

/**
 * Exact solid logo: perspective trapezoid map, 2 vertical + 1 horizontal
 * cutout grid (4 cells), teardrop pin on top-left with circular hole.
 * Fill color via currentColor.
 */
export function MapPinMark({ className }: { className?: string }) {
  const uid = useId().replace(/:/g, "");
  const maskId = `lsMapPin-${uid}`;

  return (
    <svg
      className={className}
      viewBox="0 0 80 72"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden
    >
      <defs>
        <mask id={maskId} maskUnits="userSpaceOnUse">
          <rect width="80" height="72" fill="#fff" />
          {/* Two vertical dividers */}
          <path d="M32 20 L28 54" stroke="#000" strokeWidth="2.4" />
          <path d="M50 18.5 L46 53" stroke="#000" strokeWidth="2.4" />
          {/* One horizontal divider */}
          <path d="M14 37.5 L66 33.5" stroke="#000" strokeWidth="2.4" />
          {/* Pin hole */}
          <circle cx="29" cy="18" r="4" fill="#000" />
        </mask>
      </defs>
      <g fill="currentColor" mask={`url(#${maskId})`}>
        {/* Perspective trapezoid / parallelogram map */}
        <path d="M8 50 L18 18 L70 14 L64 52 L14 56 Z" />
        {/* Solid location pin (top-left) */}
        <path d="M29 6 C22.9 6 18 10.8 18 16.8 C18 25.2 29 38 29 38 C29 38 40 25.2 40 16.8 C40 10.8 35.1 6 29 6 Z" />
      </g>
    </svg>
  );
}
