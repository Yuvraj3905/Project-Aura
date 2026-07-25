import { NextResponse } from "next/server";
import { getQueue, ProcessDocumentJob } from "@/lib/queue";
import type { Job } from "bullmq";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const STATES = ["waiting", "active", "completed", "failed", "delayed"] as const;

function toRow(job: Job<ProcessDocumentJob>, state: string) {
  return {
    id: job.id,
    name: job.name,
    state,
    retrycount: job.attemptsMade,
    retrylimit: job.opts.attempts ?? 1,
    document_id: job.data?.documentId ?? null,
    output: String(job.returnvalue ?? job.failedReason ?? "").slice(0, 200),
    createdon: new Date(job.timestamp).toISOString(),
    startedon: job.processedOn ? new Date(job.processedOn).toISOString() : null,
    completedon: job.finishedOn ? new Date(job.finishedOn).toISOString() : null,
  };
}

/** Recent BullMQ jobs (all states) for the process_document queue. */
export async function GET() {
  try {
    const queue = getQueue();
    // ponytail: per-state bucket, no per-job getState() round trip — 50/state cap.
    const buckets = await Promise.all(
      STATES.map(async (state) => {
        const jobs = await queue.getJobs([state], 0, 49);
        return jobs.map((j) => toRow(j, state));
      }),
    );
    const rows = buckets
      .flat()
      .sort((a, b) => b.createdon.localeCompare(a.createdon))
      .slice(0, 50);
    return NextResponse.json({ jobs: rows });
  } catch (err) {
    return NextResponse.json({ jobs: [], note: (err as Error).message });
  }
}
