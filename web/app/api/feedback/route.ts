import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";

const ML_SERVICE_URL = process.env.ML_SERVICE_URL ?? "http://ml-service:8100";

/** Record a 👍/👎 on an answer. Proxies to ml-service /feedback. */
export async function POST(req: NextRequest) {
  const body = await req.json();
  try {
    const upstream = await fetch(`${ML_SERVICE_URL}/feedback`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    return NextResponse.json(await upstream.json(), { status: upstream.status });
  } catch {
    return NextResponse.json({ error: "feedback unavailable" }, { status: 502 });
  }
}
