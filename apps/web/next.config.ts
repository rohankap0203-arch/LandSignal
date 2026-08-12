import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Public tunnel / phone access hits the Next origin; allow Cloudflare quick tunnels in dev.
  allowedDevOrigins: [
    "*.trycloudflare.com",
    "divided-aluminum-doc-dependence.trycloudflare.com",
  ],
  async rewrites() {
    // Server-side only — browsers must use relative /v1 so tunnels/phones work.
    const apiOrigin = process.env.LANDSIGNAL_API_ORIGIN || "http://127.0.0.1:8000";
    return [
      {
        source: "/v1/:path*",
        destination: `${apiOrigin}/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
