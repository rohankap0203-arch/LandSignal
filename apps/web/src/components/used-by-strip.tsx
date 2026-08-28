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
    name: "LandWatch",
    href: "https://www.landwatch.com",
    src: "/brands/landwatch.png",
    // Exact LandWatch LW mark
    width: 160,
    height: 160,
  },
  {
    name: "USA.gov",
    href: "https://www.usa.gov",
    src: "/brands/usa-gov.png",
    // Exact USA.gov logo from usa.gov brand assets
    width: 150,
    height: 150,
  },
] as const;

export function UsedByStrip() {
  return (
    <section className="used-by-strip" aria-label="Used by buyers on">
      <p className="used-by-label">Used by buyers on</p>
      <ul className="used-by-logos">
        {LOGOS.map((logo) => (
          <li key={logo.name}>
            <a
              className={`used-by-logo used-by-logo--${logo.name
                .toLowerCase()
                .replace(/\./g, "")
                .replace(/\s+/g, "-")}`}
              href={logo.href}
              target="_blank"
              rel="noopener noreferrer"
              title={logo.name}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={logo.src}
                alt={`${logo.name} logo`}
                width={logo.width}
                height={logo.height}
                loading="lazy"
                decoding="async"
              />
            </a>
          </li>
        ))}
      </ul>
    </section>
  );
}
