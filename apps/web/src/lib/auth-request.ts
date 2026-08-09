import { NextRequest } from "next/server";

/** Rebuild the request URL from proxy headers so Auth.js redirects match the public host. */
export function withPublicOrigin(req: NextRequest): NextRequest {
  const hostRaw = req.headers.get("x-forwarded-host") ?? req.headers.get("host");
  const protoRaw = req.headers.get("x-forwarded-proto") ?? req.nextUrl.protocol.replace(":", "");
  if (!hostRaw) return req;

  const host = hostRaw.split(",")[0]?.trim();
  const proto = (protoRaw.split(",")[0]?.trim() || "https").replace(/:$/, "");
  if (!host) return req;

  // Drop default ports; keep non-standard ones when the host lacks a port
  const publicOrigin = `${proto}://${host}`;
  const current = req.nextUrl.clone();
  if (current.origin === publicOrigin) return req;

  const next = new URL(current.pathname + current.search, publicOrigin);
  return new NextRequest(next, req);
}
