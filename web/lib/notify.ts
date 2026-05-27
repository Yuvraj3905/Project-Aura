import { pool } from "./db";

// Postgres LISTEN/NOTIFY channels bridging the worker -> WebSocket server.
export const CH_KB_READY = "kb_ready";
export const CH_KB_FAILED = "kb_failed";

export interface KbEvent {
  documentId: string;
  nChunks?: number;
  error?: string;
}

/** Emit a NOTIFY on a channel with a JSON payload. */
export async function notify(channel: string, payload: KbEvent): Promise<void> {
  await pool.query("SELECT pg_notify($1, $2)", [channel, JSON.stringify(payload)]);
}
