import PgBoss from "pg-boss";

export const PROCESS_DOCUMENT = "process_document";

let bossPromise: Promise<PgBoss> | null = null;

/**
 * Lazily start a single pg-boss instance. pg-boss creates and manages its own
 * `pgboss.*` tables in the same Postgres database. Used by the API (enqueue) and the
 * worker (consume).
 */
export function getBoss(): Promise<PgBoss> {
  if (!bossPromise) {
    const boss = new PgBoss(process.env.DATABASE_URL as string);
    boss.on("error", (err) => console.error("[pg-boss]", err));
    bossPromise = boss.start().then(() => boss);
  }
  return bossPromise;
}

export interface ProcessDocumentJob {
  documentId: string; // ml-service resolves the file path from documents.storage_path
}
