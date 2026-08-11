import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // /v1 is proxied by apps/web/src/app/v1/[...path]/route.ts so a down API
  // returns a clear 503 JSON instead of Next's raw "Internal Server Error".
};

export default nextConfig;
