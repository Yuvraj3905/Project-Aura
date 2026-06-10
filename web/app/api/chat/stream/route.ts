import { NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const ML_SERVICE_URL = process.env.ML_SERVICE_URL ?? "http://ml-service:8100";

/**
 * Stream a grounded answer to the browser. Proxies the ml-service /answer/stream SSE
 * response through unchanged (token + done + error frames). `documentIds` (optional)
 * restricts retrieval to a chosen subset of the knowledge base.
 */
export async function POST(req: NextRequest) {
  const { query, documentIds, topK, sessionId } = (await req.json()) as {
    query?: string;
    documentIds?: string[];
    topK?: number;
    sessionId?: string;
  };

  if (!query) {
    return new Response("query is required", { status: 400 });
  }

  let upstream: Response;
  try {
    upstream = await fetch(`${ML_SERVICE_URL}/answer/stream`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        query,
        document_ids: documentIds?.length ? documentIds : null,
        top_k: topK ?? null,
        // Enables the per-session sticky doc scope in ml-service.
        session_id: sessionId ?? null,
      }),
    });
  } catch {
    return new Response("event: error\ndata: {\"message\":\"knowledge engine unavailable\"}\n\n", {
      status: 200,
      headers: { "content-type": "text/event-stream" },
    });
  }

  if (!upstream.ok || !upstream.body) {
    return new Response("event: error\ndata: {\"message\":\"knowledge engine error\"}\n\n", {
      status: 200,
      headers: { "content-type": "text/event-stream" },
    });
  }

  return new Response(upstream.body, {
    headers: {
      "content-type": "text/event-stream",
      "cache-control": "no-cache",
      "x-accel-buffering": "no",
    },
  });
}
