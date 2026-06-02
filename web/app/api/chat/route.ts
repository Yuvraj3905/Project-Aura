import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";

const RASA_URL = process.env.RASA_URL ?? "http://rasa:5005";

interface RasaReply {
  recipient_id: string;
  text?: string;
  custom?: { stream?: boolean; query?: string };
}

/**
 * Proxy a chat turn to Rasa's REST channel. Rasa owns dialogue state (sender =
 * sessionId). Returns plain text replies, plus a `stream` directive if the tech_query
 * action asked the client to stream the answer over SSE.
 */
export async function POST(req: NextRequest) {
  const { sessionId, message } = (await req.json()) as {
    sessionId?: string;
    message?: string;
  };

  if (!sessionId || !message) {
    return NextResponse.json({ error: "sessionId and message are required" }, { status: 400 });
  }

  let res: Response;
  try {
    res = await fetch(`${RASA_URL}/webhooks/rest/webhook`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ sender: sessionId, message }),
    });
  } catch {
    return NextResponse.json({ error: "dialogue manager unavailable" }, { status: 502 });
  }

  if (!res.ok) {
    return NextResponse.json({ error: "dialogue manager error" }, { status: 502 });
  }

  const messages = (await res.json()) as RasaReply[];
  const streamDirective = messages.find((m) => m.custom?.stream)?.custom;

  return NextResponse.json({
    replies: messages.map((m) => m.text ?? "").filter(Boolean),
    stream: streamDirective?.stream
      ? { query: streamDirective.query ?? message }
      : null,
  });
}
