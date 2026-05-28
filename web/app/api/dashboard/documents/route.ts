import { NextResponse } from "next/server";
import { pool } from "@/lib/db";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** Recent documents with their ingestion timeline. */
export async function GET() {
  const { rows } = await pool.query(
    `SELECT id, filename, mime_type, status, n_chunks,
            left(coalesce(error, ''), 200)   AS error,
            left(coalesce(summary, ''), 200) AS summary_preview,
            created_at, updated_at
       FROM documents
       ORDER BY created_at DESC
       LIMIT 50`,
  );
  return NextResponse.json({ documents: rows });
}
