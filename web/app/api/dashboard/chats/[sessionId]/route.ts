import { NextRequest, NextResponse } from "next/server";
import { pool } from "@/lib/db";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** Full event stream for one Rasa conversation. */
export async function GET(
  _req: NextRequest,
  { params }: { params: { sessionId: string } },
) {
  try {
    const { rows } = await pool.query(
      `SELECT id, type_name, intent_name, action_name, timestamp,
              left(coalesce(data,''), 600) AS data
         FROM events
        WHERE sender_id = $1
        ORDER BY timestamp ASC
        LIMIT 500`,
      [params.sessionId],
    );
    return NextResponse.json({ sessionId: params.sessionId, events: rows });
  } catch (err) {
    return NextResponse.json(
      { sessionId: params.sessionId, events: [], note: (err as Error).message },
      { status: 200 },
    );
  }
}
