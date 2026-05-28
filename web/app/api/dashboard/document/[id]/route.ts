import { NextRequest, NextResponse } from "next/server";
import { pool } from "@/lib/db";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** Full request trail for one document: row + pg-boss job history. */
export async function GET(_req: NextRequest, { params }: { params: { id: string } }) {
  const { id } = params;

  const doc = await pool.query(
    `SELECT id, filename, mime_type, status, n_chunks, summary, error,
            created_at, updated_at
       FROM documents WHERE id = $1`,
    [id],
  );
  if (doc.rows.length === 0) {
    return NextResponse.json({ error: "not found" }, { status: 404 });
  }

  let jobs: unknown[] = [];
  try {
    const j = await pool.query(
      `SELECT id, state, retrycount, retrylimit,
              left(coalesce(output::text,''), 400) AS output,
              createdon, startedon, completedon
         FROM (
           SELECT id, state, retrycount, retrylimit, data, output,
                  createdon, startedon, completedon FROM pgboss.job
           UNION ALL
           SELECT id, state, retrycount, retrylimit, data, output,
                  createdon, startedon, completedon FROM pgboss.archive
         ) j
        WHERE j.data->>'documentId' = $1
        ORDER BY createdon ASC`,
      [id],
    );
    jobs = j.rows;
  } catch {
    /* pgboss schema may not exist yet */
  }

  return NextResponse.json({ document: doc.rows[0], jobs });
}
