import { getBoss, PROCESS_DOCUMENT, ProcessDocumentJob } from "../lib/queue";
import { notify, CH_KB_READY, CH_KB_FAILED } from "../lib/notify";

const ML_SERVICE_URL = process.env.ML_SERVICE_URL ?? "http://ml-service:8100";

/**
 * Process one document job by delegating the CPU-heavy work to the Python ml-service.
 * Throwing marks the job failed so pg-boss retries it (per the send options).
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
  const boss = await getBoss();

  // Consume jobs. The return value becomes the completion job's `response`.
  await boss.work<ProcessDocumentJob>(PROCESS_DOCUMENT, ingest as never);

  // Terminal-state notifications (fires once per job after retries are exhausted),
  // so the UI is never told "ready"/"failed" prematurely during retries.
  await boss.onComplete(PROCESS_DOCUMENT, async (job: never) => {
    const j = job as {
      data: { state: string; request: { data: ProcessDocumentJob }; response?: { nChunks?: number } };
    };
    const documentId = j.data.request?.data?.documentId;
    if (!documentId) return;

    if (j.data.state === "completed") {
      await notify(CH_KB_READY, { documentId, nChunks: j.data.response?.nChunks });
    } else {
      await notify(CH_KB_FAILED, { documentId, error: "ingestion failed" });
    }
  });

  console.log(`[worker] subscribed to "${PROCESS_DOCUMENT}", ml-service=${ML_SERVICE_URL}`);
}

main().catch((err) => {
  console.error("[worker] fatal:", err);
  process.exit(1);
});
