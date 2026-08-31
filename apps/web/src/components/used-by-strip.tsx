const LOGOS = [
  {
    name: "Land.com",
    href: "https://www.land.com",
    // Official Land.com Network lockup (green star + serif Land.com™ wordmark)
    src: "/brands/land-com-lockup.png",
    width: 270,
    height: 61,
  },
  {
    name: "Zillow",
    href: "https://www.zillow.com",
    src: "/brands/zillow.svg",
    // Exact Zillow 2024 wordmark (Wikimedia Commons / Zillow)
    width: 1000,
    height: 218,
  },
  {
    name: "Realtor.com",
    href: "https://www.realtor.com",
    src: "/brands/realtor-com.png",
    // Exact realtor.com wordmark (Wikimedia Commons)
    width: 949,
    height: 190,
  },
  {
    name: "GovDeals",
    href: "https://www.govdeals.com",
    // Official-style lockup: capitol dome above GovDeals wordmark
    src: "/brands/govdeals.png",
    srcDark: "/brands/govdeals-dark.png",
    width: 447,
    height: 233,
  },
  {
    name: "LandWatch",
    href: "https://www.landwatch.com",
    src: "/brands/landwatch.png",
    // Dark-only: white LW without plate/fringe (CSS invert makes a weird outline)
    srcDark: "/brands/landwatch-dark.png",
    width: 160,
    height: 160,
  },
] as const;

export function UsedByStrip() {
  return (
    <section className="used-by-strip" aria-label="Used by buyers on">
      <p className="used-by-label">Used by buyers on</p>
      <ul className="used-by-logos">
        {LOGOS.map((logo) => {
          const slug = logo.name.toLowerCase().replace(/\./g, "").replace(/\s+/g, "-");
          const darkSrc = "srcDark" in logo ? logo.srcDark : undefined;
          return (
            <li key={logo.name}>
              <a
                className={`used-by-logo used-by-logo--${slug}`}
                href={logo.href}
                target="_blank"
                rel="noopener noreferrer"
                title={logo.name}
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  className={darkSrc ? "used-by-logo-img used-by-logo-img--light" : undefined}
                  src={logo.src}
                  alt={`${logo.name} logo`}
                  width={logo.width}
                  height={logo.height}
                  loading="lazy"
                  decoding="async"
                />
                {darkSrc ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    className="used-by-logo-img used-by-logo-img--dark"
                    src={darkSrc}
                    alt=""
                    aria-hidden
                    width={logo.width}
                    height={logo.height}
                    loading="lazy"
                    decoding="async"
                  />
                ) : null}
              </a>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
