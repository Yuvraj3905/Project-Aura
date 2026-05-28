import { NextResponse } from "next/server";
import { pool } from "@/lib/db";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** Recent Rasa conversation sessions. Rasa creates the `events` table on first run. */
export async function GET() {
  try {
    const { rows } = await pool.query(
      `SELECT sender_id,
              count(*)                         AS events,
              count(*) FILTER (WHERE type_name = 'user')   AS user_turns,
              count(*) FILTER (WHERE type_name = 'bot')    AS bot_turns,
              min(timestamp)                  AS first_ts,
              max(timestamp)                  AS last_ts
         FROM events
         GROUP BY sender_id
         ORDER BY max(timestamp) DESC
         LIMIT 50`,
    );
    return NextResponse.json({ sessions: rows });
  } catch (err) {
    return NextResponse.json({ sessions: [], note: (err as Error).message });
  }
}
