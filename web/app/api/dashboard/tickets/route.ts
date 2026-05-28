import { NextResponse } from "next/server";
import { pool } from "@/lib/db";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  const { rows } = await pool.query(
    `SELECT id, email, left(coalesce(subject,''), 80) AS subject,
            left(description, 200) AS description,
            session_id, status, created_at
       FROM support_tickets
       ORDER BY created_at DESC
       LIMIT 50`,
  );
  return NextResponse.json({ tickets: rows });
}
