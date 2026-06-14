import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";

const ML_SERVICE_URL = process.env.ML_SERVICE_URL ?? "http://ml-service:8100";

/**
 * Dispose a chat session's server-side state. Currently clears the sticky document
 * scope in ml-service so the next (new) session starts with global retrieval instead
 * of inheriting the disposed conversation's locked documents. Rasa's tracker for the
 * old sender id is left to expire on its own (a new sessionId starts a fresh tracker).
 */
export async function POST(req: NextRequest) {
  const { sessionId } = (await req.json()) as { sessionId?: string };
  if (!sessionId) {
    return NextResponse.json({ error: "sessionId is required" }, { status: 400 });
  }

  try {
    await fetch(`${ML_SERVICE_URL}/session/${encodeURIComponent(sessionId)}/scope`, {
      method: "DELETE",
    });
  } catch {
    // Best-effort cleanup — the client still resets locally even if this fails.
    return NextResponse.json({ ok: false }, { status: 200 });
  }

  return NextResponse.json({ ok: true });
}
