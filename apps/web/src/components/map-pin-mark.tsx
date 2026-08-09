"use client";

import { useId } from "react";

/**
 * Exact solid map + pin mark (filled board, thin cutout grid, solid pin with hole).
 * Color via currentColor.
 */
export function MapPinMark({ className }: { className?: string }) {
  const uid = useId().replace(/:/g, "");
  const maskId = `mapPinMask-${uid}`;

  return (
    <svg
      className={className}
      viewBox="0 0 64 56"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden
    >
      <defs>
        <mask id={maskId} maskUnits="userSpaceOnUse">
          <rect x="0" y="0" width="64" height="56" fill="#fff" />
          {/* Thin divider “roads” cut out of the solid map */}
          <path
            d="M24 16.2 L20.2 41.8"
            stroke="#000"
            strokeWidth="2.1"
            strokeLinecap="butt"
          />
          <path
            d="M40.5 15.2 L36.8 41"
            stroke="#000"
            strokeWidth="2.1"
            strokeLinecap="butt"
          />
          <path
            d="M11.5 29.2 L54.5 25.4"
            stroke="#000"
            strokeWidth="2.1"
            strokeLinecap="butt"
          />
          {/* Pin hole */}
          <circle cx="23.5" cy="15.2" r="3.35" fill="#000" />
        </mask>
      </defs>

      <g fill="currentColor" mask={`url(#${maskId})`}>
        {/* Perspective trapezoid map */}
        <path d="M6.5 40.5 L16.5 15.5 L57.5 12.5 L51.5 42.5 L10.5 45.5 Z" />
        {/* Solid teardrop pin */}
        <path d="M23.5 5.2 C18.55 5.2 14.5 9.15 14.5 14.05 C14.5 20.9 23.5 31.2 23.5 31.2 C23.5 31.2 32.5 20.9 32.5 14.05 C32.5 9.15 28.45 5.2 23.5 5.2 Z" />
      </g>
    </svg>
  );
}
