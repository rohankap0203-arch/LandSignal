import type { ReactNode } from "react";

/** Compact “Used by users of” credibility strip — monochrome wordmarks. */

const LOGOS: Array<{
  name: string;
  href: string;
  mark: ReactNode;
}> = [
  {
    name: "Land.com",
    href: "https://www.land.com",
    mark: (
      <svg viewBox="0 0 120 28" role="img" aria-label="Land.com">
        <title>Land.com</title>
        <text
          x="0"
          y="20"
          fill="currentColor"
          fontFamily="Georgia, 'Times New Roman', serif"
          fontSize="18"
          fontWeight="700"
          letterSpacing="-0.02em"
        >
          Land.com
        </text>
      </svg>
    ),
  },
  {
    name: "Zillow",
    href: "https://www.zillow.com",
    mark: (
      <svg viewBox="0 0 110 28" role="img" aria-label="Zillow">
        <title>Zillow</title>
        <path
          fill="currentColor"
          d="M8.2 6.2h14.6l-12.4 15.6h12.8V25H6.4l12.5-15.6H8.2V6.2z"
        />
        <text
          x="28"
          y="20"
          fill="currentColor"
          fontFamily="Arial, Helvetica, sans-serif"
          fontSize="15"
          fontWeight="700"
          letterSpacing="-0.03em"
        >
          illow
        </text>
      </svg>
    ),
  },
  {
    name: "Realtor.com",
    href: "https://www.realtor.com",
    mark: (
      <svg viewBox="0 0 138 28" role="img" aria-label="Realtor.com">
        <title>Realtor.com</title>
        <circle cx="11" cy="14" r="10" fill="currentColor" opacity="0.92" />
        <text
          x="11"
          y="18.5"
          textAnchor="middle"
          fill="#fff"
          fontFamily="Arial, Helvetica, sans-serif"
          fontSize="13"
          fontWeight="800"
        >
          R
        </text>
        <text
          x="26"
          y="19"
          fill="currentColor"
          fontFamily="Arial, Helvetica, sans-serif"
          fontSize="13.5"
          fontWeight="700"
          letterSpacing="-0.02em"
        >
          ealtor.com
        </text>
      </svg>
    ),
  },
  {
    name: "LandWatch",
    href: "https://www.landwatch.com",
    mark: (
      <svg viewBox="0 0 148 28" role="img" aria-label="LandWatch">
        <title>LandWatch</title>
        <text
          x="0"
          y="19.5"
          fill="currentColor"
          fontFamily="Arial, Helvetica, sans-serif"
          fontSize="14"
          fontWeight="800"
          letterSpacing="0.01em"
        >
          LAND
        </text>
        <text
          x="52"
          y="19.5"
          fill="currentColor"
          fontFamily="Arial, Helvetica, sans-serif"
          fontSize="14"
          fontWeight="500"
          letterSpacing="0.04em"
          opacity="0.85"
        >
          WATCH
        </text>
      </svg>
    ),
  },
  {
    name: "USA.gov",
    href: "https://www.usa.gov",
    mark: (
      <svg viewBox="0 0 108 28" role="img" aria-label="USA.gov">
        <title>USA.gov</title>
        <rect x="1" y="4" width="20" height="20" rx="3" fill="currentColor" opacity="0.9" />
        <path
          fill="#fff"
          d="M5.2 18.8 11 7.6l5.8 11.2h-2.2l-1.1-2.2H8.5l-1.1 2.2H5.2zm4.4-4.2h3.8L11 9.8l-1.4 4.8z"
        />
        <text
          x="28"
          y="19.5"
          fill="currentColor"
          fontFamily="Arial, Helvetica, sans-serif"
          fontSize="14"
          fontWeight="700"
          letterSpacing="-0.01em"
        >
          USA.gov
        </text>
      </svg>
    ),
  },
];

export function UsedByStrip() {
  return (
    <section className="used-by-strip" aria-label="Used by users of">
      <p className="used-by-label">Used by users of</p>
      <ul className="used-by-logos">
        {LOGOS.map((logo) => (
          <li key={logo.name}>
            <a
              className="used-by-logo"
              href={logo.href}
              target="_blank"
              rel="noopener noreferrer"
              title={logo.name}
            >
              {logo.mark}
            </a>
          </li>
        ))}
      </ul>
    </section>
  );
}
