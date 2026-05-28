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
  const wss = new WebSocketServer({ server, path: "/ws" });

  function broadcast(obj: unknown): void {
    const msg = JSON.stringify(obj);
    for (const client of wss.clients) {
      if (client.readyState === WebSocket.OPEN) client.send(msg);
    }
  }

  // Dedicated connection for LISTEN — pg Pool clients can't be used for notifications.
  const listener = new Client({ connectionString: process.env.DATABASE_URL });
  await listener.connect();
  await listener.query(`LISTEN ${CH_KB_READY}`);
  await listener.query(`LISTEN ${CH_KB_FAILED}`);
  listener.on("notification", (n) => {
    const payload = n.payload ? JSON.parse(n.payload) : {};
    broadcast({ type: n.channel, ...payload });
  });

  server.listen(port, () => {
    console.log(`[web] listening on :${port} (ws path /ws)`);
  });
}

main().catch((err) => {
  console.error("[web] fatal:", err);
  process.exit(1);
});
