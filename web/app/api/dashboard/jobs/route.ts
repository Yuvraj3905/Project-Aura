import { NextResponse } from "next/server";
import { pool } from "@/lib/db";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** Recent pg-boss jobs (active + archived). Tolerates missing schema on first boot. */
export async function GET() {
  try {
    const { rows } = await pool.query(
      `SELECT id, name, state, retrycount, retrylimit,
              data->>'documentId'             AS document_id,
              left(coalesce(output::text,''), 200) AS output,
              createdon, startedon, completedon
         FROM (
           SELECT id, name, state, retrycount, retrylimit, data, output,
                  createdon, startedon, completedon FROM pgboss.job
           UNION ALL
           SELECT id, name, state, retrycount, retrylimit, data, output,
                  createdon, startedon, completedon FROM pgboss.archive
         ) j
         ORDER BY createdon DESC
         LIMIT 50`,
    );
    return NextResponse.json({ jobs: rows });
  } catch (err) {
    // pgboss schema may not exist yet (no uploads since fresh boot).
    return NextResponse.json({ jobs: [], note: (err as Error).message });
  }
}
