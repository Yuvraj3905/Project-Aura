import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const ML_SERVICE_URL = process.env.ML_SERVICE_URL ?? "http://ml-service:8100";

/** Transition a ticket's status. Writes go through ml-service (single source of truth). */
export async function PATCH(req: NextRequest, { params }: { params: { id: string } }) {
  const { status } = (await req.json()) as { status?: string };
  if (!status) {
    return NextResponse.json({ error: "status required" }, { status: 400 });
  }

  let res: Response;
  try {
    res = await fetch(`${ML_SERVICE_URL}/tickets/${params.id}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ status }),
    });
  } catch {
    return NextResponse.json({ error: "ml-service unavailable" }, { status: 502 });
  }

  const body = await res.json().catch(() => ({}));
  return NextResponse.json(body, { status: res.status });
}
