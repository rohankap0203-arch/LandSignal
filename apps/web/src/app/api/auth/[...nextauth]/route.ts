import { handlers } from "@/auth";
import { withPublicOrigin } from "@/lib/auth-request";
import type { NextRequest } from "next/server";

export const GET = (req: NextRequest) => handlers.GET(withPublicOrigin(req));
export const POST = (req: NextRequest) => handlers.POST(withPublicOrigin(req));
