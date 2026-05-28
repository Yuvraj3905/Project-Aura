"use client";

import { useEffect, useState, useCallback } from "react";

const POLL_MS = 4000;
const STATUS_COLOR: Record<string, string> = {
  uploaded: "#888",
  processing: "#b8860b",
  ready: "#1a7f37",
  failed: "#b00020",
  created: "#888",
  active: "#0969da",
  completed: "#1a7f37",
  expired: "#b00020",
  retry: "#b8860b",
};

interface Doc {
  id: string;
  filename: string;
  status: string;
  n_chunks: number;
  error: string;
  summary_preview?: string; // list endpoint
  summary?: string;         // detail endpoint
  created_at: string;
  updated_at: string;
}
interface Job {
  id: string;
  name: string;
  state: string;
  retrycount: number;
  retrylimit: number;
  document_id: string | null;
  output: string;
  createdon: string;
  startedon: string | null;
  completedon: string | null;
}
interface Ticket {
  id: string;
  email: string;
  subject: string;
  description: string;
  session_id: string | null;
  status: string;
  created_at: string;
}
interface ChatSession {
  sender_id: string;
  events: number;
  user_turns: number;
  bot_turns: number;
  first_ts: number;
  last_ts: number;
}
interface DocTrail {
  document: Doc;
  jobs: Job[];
}
interface EventRow {
  id: number;
  type_name: string;
  intent_name: string | null;
  action_name: string | null;
  timestamp: number;
  data: string;
}

function fmtAge(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  if (ms < 60_000) return `${Math.floor(ms / 1000)}s ago`;
  if (ms < 3_600_000) return `${Math.floor(ms / 60_000)}m ago`;
  if (ms < 86_400_000) return `${Math.floor(ms / 3_600_000)}h ago`;
  return new Date(iso).toLocaleString();
}
function fmtAgeEpoch(epochSec: number): string {
  return fmtAge(new Date(epochSec * 1000).toISOString());
}
function pill(status: string) {
  return (
    <span
      style={{
        display: "inline-block",
        padding: "2px 8px",
        borderRadius: 12,
        background: STATUS_COLOR[status] ?? "#444",
        color: "white",
        fontSize: 12,
      }}
    >
      {status}
    </span>
  );
}

export default function Dashboard() {
  const [docs, setDocs] = useState<Doc[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [filter, setFilter] = useState("");
  const [selectedDoc, setSelectedDoc] = useState<DocTrail | null>(null);
  const [selectedSession, setSelectedSession] = useState<{ id: string; events: EventRow[] } | null>(null);

  const refresh = useCallback(async () => {
    const [d, j, t, c] = await Promise.all([
      fetch("/api/dashboard/documents").then((r) => r.json()),
      fetch("/api/dashboard/jobs").then((r) => r.json()),
      fetch("/api/dashboard/tickets").then((r) => r.json()),
      fetch("/api/dashboard/chats").then((r) => r.json()),
    ]);
    setDocs(d.documents ?? []);
    setJobs(j.jobs ?? []);
    setTickets(t.tickets ?? []);
    setSessions(c.sessions ?? []);
  }, []);

  useEffect(() => {
    refresh();
    const i = setInterval(refresh, POLL_MS);
    return () => clearInterval(i);
  }, [refresh]);

  async function openDoc(id: string) {
    const r = await fetch(`/api/dashboard/document/${id}`).then((r) => r.json());
    setSelectedDoc(r);
  }
  async function openSession(id: string) {
    const r = await fetch(`/api/dashboard/chats/${encodeURIComponent(id)}`).then((r) => r.json());
    setSelectedSession({ id, events: r.events ?? [] });
  }

  const f = filter.trim().toLowerCase();
  const filteredDocs = !f
    ? docs
    : docs.filter((d) => d.id.toLowerCase().includes(f) || d.filename.toLowerCase().includes(f));
  const filteredJobs = !f
    ? jobs
    : jobs.filter((j) => (j.document_id ?? "").toLowerCase().includes(f));
  const filteredTickets = !f
    ? tickets
    : tickets.filter(
        (t) =>
          (t.session_id ?? "").toLowerCase().includes(f) ||
          t.email.toLowerCase().includes(f),
      );
  const filteredSessions = !f
    ? sessions
    : sessions.filter((s) => s.sender_id.toLowerCase().includes(f));

  return (
    <main style={{ fontFamily: "system-ui", maxWidth: 1200, margin: "0 auto", padding: "1.5rem" }}>
      <header style={{ display: "flex", alignItems: "baseline", gap: 16 }}>
        <h1 style={{ margin: 0 }}>Aura · Dashboard</h1>
        <span style={{ color: "#666" }}>auto-refresh {POLL_MS / 1000}s</span>
        <span style={{ marginLeft: "auto", display: "flex", gap: 12 }}>
          <a href="/" style={{ color: "#0969da" }}>← chat</a>
          <a href="http://localhost:9999" target="_blank" rel="noreferrer" style={{ color: "#0969da" }}>
            raw logs ↗
          </a>
        </span>
      </header>

      <input
        placeholder="Filter by documentId / sessionId / email…"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        style={{ width: "100%", padding: 8, margin: "12px 0", border: "1px solid #ccc", borderRadius: 6 }}
      />

      <Section title={`Documents (${filteredDocs.length})`}>
        <Table
          headers={["filename", "status", "chunks", "updated", "id"]}
          rows={filteredDocs.map((d) => [
            d.filename,
            pill(d.status),
            d.n_chunks,
            fmtAge(d.updated_at),
            <button key={d.id} onClick={() => openDoc(d.id)} style={linkBtn}>
              {d.id.slice(0, 8)}…
            </button>,
          ])}
        />
      </Section>

      <Section title={`pg-boss jobs (${filteredJobs.length})`}>
        <Table
          headers={["queue", "state", "retries", "documentId", "created", "completed"]}
          rows={filteredJobs.map((j) => [
            j.name,
            pill(j.state),
            `${j.retrycount}/${j.retrylimit}`,
            j.document_id ? (
              <button key={j.id} onClick={() => openDoc(j.document_id!)} style={linkBtn}>
                {j.document_id.slice(0, 8)}…
              </button>
            ) : (
              "—"
            ),
            fmtAge(j.createdon),
            j.completedon ? fmtAge(j.completedon) : "—",
          ])}
        />
      </Section>

      <Section title={`Chat sessions (${filteredSessions.length})`}>
        <Table
          headers={["sessionId", "events", "user", "bot", "last"]}
          rows={filteredSessions.map((s) => [
            <button key={s.sender_id} onClick={() => openSession(s.sender_id)} style={linkBtn}>
              {s.sender_id}
            </button>,
            s.events,
            s.user_turns,
            s.bot_turns,
            fmtAgeEpoch(s.last_ts),
          ])}
        />
      </Section>

      <Section title={`Tickets (${filteredTickets.length})`}>
        <Table
          headers={["email", "description", "session", "status", "created"]}
          rows={filteredTickets.map((t) => [
            t.email,
            t.description,
            t.session_id ?? "—",
            pill(t.status),
            fmtAge(t.created_at),
          ])}
        />
      </Section>

      {selectedDoc && <DocPanel trail={selectedDoc} onClose={() => setSelectedDoc(null)} />}
      {selectedSession && (
        <SessionPanel session={selectedSession} onClose={() => setSelectedSession(null)} />
      )}
    </main>
  );
}

const linkBtn: React.CSSProperties = {
  background: "none",
  border: "none",
  color: "#0969da",
  cursor: "pointer",
  padding: 0,
  font: "inherit",
};

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section style={{ border: "1px solid #ddd", borderRadius: 8, padding: 12, marginTop: 14 }}>
      <h2 style={{ fontSize: "1rem", margin: "0 0 8px" }}>{title}</h2>
      {children}
    </section>
  );
}

function Table({ headers, rows }: { headers: string[]; rows: React.ReactNode[][] }) {
  if (rows.length === 0) return <div style={{ color: "#888" }}>—</div>;
  return (
    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
      <thead>
        <tr>
          {headers.map((h) => (
            <th key={h} style={{ textAlign: "left", padding: "4px 8px", color: "#666", fontWeight: 600 }}>
              {h}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i} style={{ borderTop: "1px solid #eee" }}>
            {r.map((cell, j) => (
              <td key={j} style={{ padding: "6px 8px", verticalAlign: "top" }}>
                {cell}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function DocPanel({ trail, onClose }: { trail: DocTrail; onClose: () => void }) {
  return (
    <Overlay onClose={onClose} title={`Document · ${trail.document.filename}`}>
      <p>
        <strong>id:</strong> <code>{trail.document.id}</code> · {pill(trail.document.status)} ·{" "}
        chunks {trail.document.n_chunks}
      </p>
      {trail.document.error && (
        <pre style={preErr}>error: {trail.document.error}</pre>
      )}
      {trail.document.summary && (
        <details>
          <summary>doc-level summary (prepended to every chunk)</summary>
          <pre style={preBox}>{trail.document.summary}</pre>
        </details>
      )}
      <h3 style={{ fontSize: "0.95rem", marginTop: 12 }}>Job trail</h3>
      <Table
        headers={["state", "retries", "created", "started", "completed", "output"]}
        rows={trail.jobs.map((j) => [
          pill(j.state),
          `${j.retrycount}/${j.retrylimit}`,
          fmtAge(j.createdon),
          j.startedon ? fmtAge(j.startedon) : "—",
          j.completedon ? fmtAge(j.completedon) : "—",
          j.output ? <code style={{ fontSize: 12 }}>{j.output}</code> : "—",
        ])}
      />
    </Overlay>
  );
}

function SessionPanel({
  session,
  onClose,
}: {
  session: { id: string; events: EventRow[] };
  onClose: () => void;
}) {
  return (
    <Overlay onClose={onClose} title={`Chat session · ${session.id}`}>
      <Table
        headers={["ts", "type", "intent/action"]}
        rows={session.events.map((e) => [
          new Date(e.timestamp * 1000).toLocaleTimeString(),
          e.type_name,
          e.intent_name || e.action_name || "—",
        ])}
      />
    </Overlay>
  );
}

function Overlay({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.4)",
        display: "flex",
        justifyContent: "center",
        alignItems: "flex-start",
        padding: 40,
        zIndex: 50,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "white",
          borderRadius: 10,
          padding: 20,
          maxWidth: 900,
          width: "100%",
          maxHeight: "85vh",
          overflowY: "auto",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h2 style={{ margin: 0, fontSize: "1.05rem" }}>{title}</h2>
          <button onClick={onClose} style={{ padding: "4px 10px" }}>
            close
          </button>
        </div>
        <div style={{ marginTop: 12 }}>{children}</div>
      </div>
    </div>
  );
}

const preBox: React.CSSProperties = {
  background: "#f6f8fa",
  padding: 10,
  borderRadius: 6,
  whiteSpace: "pre-wrap",
  fontSize: 13,
};
const preErr: React.CSSProperties = { ...preBox, background: "#fdecea", color: "#b00020" };
