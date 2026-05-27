import { NextRequest, NextResponse } from "next/server";
import { pool } from "@/lib/db";

export const runtime = "nodejs";

/** Status poll — WebSocket fallback for ingestion progress. */
export async function GET(_req: NextRequest, { params }: { params: { id: string } }) {
  const { rows } = await pool.query(
    "SELECT id, filename, status, n_chunks, error, updated_at FROM documents WHERE id = $1",
    [params.id],
  );
  if (rows.length === 0) {
    return NextResponse.json({ error: "not found" }, { status: 404 });
  }
  return NextResponse.json(rows[0]);
}
