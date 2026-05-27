import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";

const RASA_URL = process.env.RASA_URL ?? "http://rasa:5005";

interface RasaReply {
  recipient_id: string;
  text?: string;
}

/** Proxy a chat turn to Rasa's REST channel. Rasa owns dialogue state (sender = sessionId). */
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

  const replies = (await res.json()) as RasaReply[];
  return NextResponse.json({
    replies: replies.map((r) => r.text ?? "").filter(Boolean),
  });
}
