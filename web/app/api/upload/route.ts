import { NextRequest, NextResponse } from "next/server";
import { randomUUID } from "node:crypto";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { pool } from "@/lib/db";
import { getQueue, PROCESS_DOCUMENT } from "@/lib/queue";

export const runtime = "nodejs";

const UPLOAD_DIR = process.env.UPLOAD_DIR ?? "/data/uploads";
const MAX_BYTES = 50 * 1024 * 1024; // 50 MB
const ALLOWED_MIME = new Set([
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "text/plain",
  "text/markdown",
]);
const ALLOWED_EXT = new Set([".pdf", ".docx", ".txt", ".md"]);

/**
 * Accept a document upload, persist it to the shared volume, record it, and enqueue a
 * `process_document` job. Returns 202 immediately — ingestion runs asynchronously.
 */
export async function POST(req: NextRequest) {
  const form = await req.formData();
  const file = form.get("file");

  if (!(file instanceof File)) {
    return NextResponse.json({ error: "missing 'file' field" }, { status: 400 });
  }
  if (file.size > MAX_BYTES) {
    return NextResponse.json({ error: "file too large (max 50MB)" }, { status: 413 });
  }

  const ext = path.extname(file.name).toLowerCase();
  const mime = file.type || "application/octet-stream";
  if (!ALLOWED_MIME.has(mime) && !ALLOWED_EXT.has(ext)) {
    return NextResponse.json(
      { error: `unsupported type '${mime || ext}' (pdf, docx, txt, md)` },
      { status: 415 },
    );
  }

  // Server-generated UUID is the document id AND the storage filename — the client's
  // filename is kept only for display, never used as a path (path-traversal safety).
  const id = randomUUID();
  const storageName = `${id}${ext}`; // basename only; ml-service resolves under its root
  await mkdir(UPLOAD_DIR, { recursive: true });
  await writeFile(path.join(UPLOAD_DIR, storageName), Buffer.from(await file.arrayBuffer()));

  // Record the document BEFORE enqueuing, so the worker is guaranteed to find the row.
  await pool.query(
    "INSERT INTO documents (id, filename, storage_path, mime_type, status) VALUES ($1, $2, $3, $4, 'uploaded')",
    [id, file.name, storageName, mime],
  );

  // Enqueue the heavy work. attempts + exponential backoff: transient failures (e.g.
  // Ollama briefly down) are retried.
  const queue = getQueue();
  await queue.add(
    PROCESS_DOCUMENT,
    { documentId: id },
    { attempts: 3, backoff: { type: "exponential", delay: 5000 } },
  );

  // 202 Accepted: work is queued, not done. The client learns completion over WebSocket.
  return NextResponse.json({ documentId: id, status: "uploaded" }, { status: 202 });
}
