import { Worker } from "bullmq";
import { makeQueueConnection, PROCESS_DOCUMENT, ProcessDocumentJob } from "../lib/queue";
import { notify, CH_KB_READY, CH_KB_FAILED } from "../lib/notify";

const ML_SERVICE_URL = process.env.ML_SERVICE_URL ?? "http://ml-service:8100";

/**
 * Process one document job by delegating the CPU-heavy work to the Python ml-service.
 * Throwing marks the job failed so BullMQ retries it (per the queue's job options).
 */
async function ingest(job: { data: ProcessDocumentJob }): Promise<{ nChunks: number }> {
  const { documentId } = job.data;
  const res = await fetch(`${ML_SERVICE_URL}/ingest`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ document_id: documentId }),
  });
  if (!res.ok) {
    throw new Error(`ml-service /ingest ${res.status}: ${await res.text()}`);
  }
  const data = (await res.json()) as { n_chunks: number };
  return { nChunks: data.n_chunks };
}

async function main(): Promise<void> {
  const worker = new Worker<ProcessDocumentJob, { nChunks: number }>(
    PROCESS_DOCUMENT,
    ingest,
    { connection: makeQueueConnection() },
  );

  // Fires once per job, only after it actually succeeds.
  worker.on("completed", async (job, result) => {
    await notify(CH_KB_READY, { documentId: job.data.documentId, nChunks: result?.nChunks });
  });

  // Fires on every failed attempt — only notify once retries are exhausted, so the UI
  // is never told "failed" prematurely while a retry is still pending.
  worker.on("failed", async (job, err) => {
    if (!job) return;
    const attempts = job.opts.attempts ?? 1;
    if (job.attemptsMade < attempts) return;
    await notify(CH_KB_FAILED, { documentId: job.data.documentId, error: err.message });
  });

  worker.on("error", (err) => console.error("[worker]", err));

  console.log(`[worker] subscribed to "${PROCESS_DOCUMENT}", ml-service=${ML_SERVICE_URL}`);
}

main().catch((err) => {
  console.error("[worker] fatal:", err);
  process.exit(1);
});
