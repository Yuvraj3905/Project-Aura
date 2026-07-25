import { Queue } from "bullmq";
import IORedis from "ioredis";

export const PROCESS_DOCUMENT = "process_document";

export interface ProcessDocumentJob {
  documentId: string; // ml-service resolves the file path from documents.storage_path
}

// Separate DB index from the ml-service query/answer cache (db 0) so a `FLUSHDB` on
// either doesn't touch the other. BullMQ requires maxRetriesPerRequest: null on the
// blocking connection it uses internally.
export function makeQueueConnection(): IORedis {
  return new IORedis(process.env.REDIS_URL ?? "redis://redis:6379/1", {
    maxRetriesPerRequest: null,
  });
}

let queue: Queue<ProcessDocumentJob> | null = null;

/** Lazily create a single BullMQ queue instance, shared by API routes that enqueue/inspect jobs. */
export function getQueue(): Queue<ProcessDocumentJob> {
  if (!queue) {
    queue = new Queue<ProcessDocumentJob>(PROCESS_DOCUMENT, { connection: makeQueueConnection() });
  }
  return queue;
}
