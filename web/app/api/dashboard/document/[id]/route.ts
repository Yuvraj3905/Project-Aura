import { NextRequest, NextResponse } from "next/server";
import { pool } from "@/lib/db";
import { getQueue, ProcessDocumentJob } from "@/lib/queue";
import type { Job } from "bullmq";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const STATES = ["waiting", "active", "completed", "failed", "delayed"] as const;

function toRow(job: Job<ProcessDocumentJob>, state: string) {
  return {
    id: job.id,
    state,
    retrycount: job.attemptsMade,
    retrylimit: job.opts.attempts ?? 1,
    output: String(job.returnvalue ?? job.failedReason ?? "").slice(0, 400),
    createdon: new Date(job.timestamp).toISOString(),
    startedon: job.processedOn ? new Date(job.processedOn).toISOString() : null,
    completedon: job.finishedOn ? new Date(job.finishedOn).toISOString() : null,
  };
}

/** Full request trail for one document: row + BullMQ job history. */
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
    const queue = getQueue();
    // ponytail: per-state bucket + filter by documentId, no job index by document.
    const buckets = await Promise.all(
      STATES.map(async (state) => {
        const found = await queue.getJobs([state], 0, 49);
        return found.filter((j) => j.data?.documentId === id).map((j) => toRow(j, state));
      }),
    );
    jobs = buckets.flat().sort((a, b) => a.createdon.localeCompare(b.createdon));
  } catch {
    /* redis unreachable — degrade to doc row only */
  }

  return NextResponse.json({ document: doc.rows[0], jobs });
}
