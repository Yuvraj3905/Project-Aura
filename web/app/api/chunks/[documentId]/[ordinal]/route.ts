import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";

const ML_SERVICE_URL = process.env.ML_SERVICE_URL ?? "http://ml-service:8100";

/** Fetch the source text behind a citation so the UI can show what an answer was grounded in. */
export async function GET(
  _req: NextRequest,
  { params }: { params: { documentId: string; ordinal: string } },
) {
  let upstream: Response;
  try {
    upstream = await fetch(
      `${ML_SERVICE_URL}/chunks/${params.documentId}/${params.ordinal}`,
    );
  } catch {
    return NextResponse.json({ error: "source unavailable" }, { status: 502 });
  }
  if (!upstream.ok) {
    return NextResponse.json({ error: "source not found" }, { status: upstream.status });
  }
  return NextResponse.json(await upstream.json());
}
