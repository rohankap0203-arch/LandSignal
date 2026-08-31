import { NextResponse } from "next/server";
import { createUser } from "@/lib/local-users";

export async function POST(req: Request) {
  let body: { email?: string; password?: string; name?: string };
  try {
    body = (await req.json()) as { email?: string; password?: string; name?: string };
  } catch {
    return NextResponse.json({ detail: "Invalid request body." }, { status: 400 });
  }

  try {
    const user = createUser({
      email: String(body.email || ""),
      password: String(body.password || ""),
      name: String(body.name || ""),
    });
    return NextResponse.json({
      ok: true,
      user: { id: user.id, email: user.email, name: user.name },
    });
  } catch (err) {
    const detail = err instanceof Error ? err.message : "Could not create account.";
    return NextResponse.json({ detail }, { status: 400 });
  }
}
