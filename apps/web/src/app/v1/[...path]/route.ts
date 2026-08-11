import { NextRequest, NextResponse } from "next/server";

const API_ORIGIN = process.env.LANDSIGNAL_API_ORIGIN || "http://127.0.0.1:8000";

/** Headers that must not be forwarded (request or response). */
const HOP_BY_HOP = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailers",
  "transfer-encoding",
  "upgrade",
  "host",
  "content-length",
  // Node fetch auto-decompresses; forwarding these with a decoded body breaks browsers
  // ("Failed to fetch") — which Show matches used to surface as a connection error.
  "content-encoding",
  "accept-encoding",
]);

async function proxy(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  const incoming = new URL(req.url);
  const target = `${API_ORIGIN}/v1/${path.map(encodeURIComponent).join("/")}${incoming.search}`;

  const headers = new Headers();
  req.headers.forEach((value, key) => {
    if (!HOP_BY_HOP.has(key.toLowerCase())) headers.set(key, value);
  });
  // Ask upstream for identity encoding so we never re-label a decoded body as gzip.
  headers.set("accept-encoding", "identity");

  const init: RequestInit & { duplex?: "half" } = {
    method: req.method,
    headers,
    cache: "no-store",
    redirect: "manual",
  };

  if (req.method !== "GET" && req.method !== "HEAD") {
    init.body = await req.arrayBuffer();
    init.duplex = "half";
  }

  try {
    const upstream = await fetch(target, init);
    const body = await upstream.arrayBuffer();
    const outHeaders = new Headers();
    upstream.headers.forEach((value, key) => {
      if (!HOP_BY_HOP.has(key.toLowerCase())) outHeaders.set(key, value);
    });
    return new NextResponse(body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: outHeaders,
    });
  } catch {
    return NextResponse.json(
      {
        detail:
          "LandSignal API is not reachable on port 8000. Start it with `npm run dev:api`, then try Show matches again.",
      },
      { status: 503 },
    );
  }
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
export const OPTIONS = proxy;
