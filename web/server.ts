// Custom Next.js server. Next's built-in server doesn't expose the HTTP server, so we
// run our own to (a) attach a WebSocket server for live ingestion-status push, and
// (b) hold a dedicated Postgres LISTEN connection that bridges DB NOTIFY → WebSocket.
// Everything else (pages, API routes) is delegated to Next's request handler.
import { createServer } from "node:http";
import next from "next";
import { WebSocketServer, WebSocket } from "ws";
import { Client } from "pg";
import { CH_KB_READY, CH_KB_FAILED } from "./lib/notify";

const port = Number(process.env.PORT ?? 3100);
const dev = process.env.NODE_ENV !== "production";
const app = next({ dev });
const handle = app.getRequestHandler();

async function main(): Promise<void> {
  await app.prepare();

  const server = createServer((req, res) => {
    // We are not behind a trusted proxy — stamp the real socket address as
    // X-Forwarded-For so Edge middleware can do reliable loopback / IP checks.
    // Overwrite any client-supplied value to block spoofing.
    req.headers["x-forwarded-for"] = req.socket.remoteAddress ?? "";
    return handle(req, res);
  });
  // WebSocket endpoint at /ws — browsers connect here to receive KB-ready/-failed pushes.
  const wss = new WebSocketServer({ server, path: "/ws" });

  // Fan a payload out to every currently-open WebSocket client.
  function broadcast(obj: unknown): void {
    const msg = JSON.stringify(obj);
    for (const client of wss.clients) {
      if (client.readyState === WebSocket.OPEN) client.send(msg);
    }
  }

  // Dedicated connection for LISTEN — a pooled client can't be used (the pool would
  // reassign it mid-listen). The worker emits NOTIFY on these channels when a document
  // finishes ingesting; we forward each straight to all WebSocket clients.
  const listener = new Client({ connectionString: process.env.DATABASE_URL });
  await listener.connect();
  await listener.query(`LISTEN ${CH_KB_READY}`);
  await listener.query(`LISTEN ${CH_KB_FAILED}`);
  listener.on("notification", (n) => {
    const payload = n.payload ? JSON.parse(n.payload) : {};
    broadcast({ type: n.channel, ...payload }); // type = channel name (kb_ready / kb_failed)
  });

  server.listen(port, () => {
    console.log(`[web] listening on :${port} (ws path /ws)`);
  });
}

main().catch((err) => {
  console.error("[web] fatal:", err);
  process.exit(1);
});
