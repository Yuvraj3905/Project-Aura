"use client";

import { useEffect, useState, useCallback } from "react";

const POLL_MS = 4000;
const STATUS_COLOR: Record<string, string> = {
  uploaded: "#888",
  processing: "#b8860b",
  ready: "#1a7f37",
  failed: "#b00020",
  created: "#888",
  waiting: "#888",
  active: "#0969da",
  completed: "#1a7f37",
  delayed: "#b8860b",
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
interface UsageStats {
  total_requests: number; llm_calls: number; cache_hits: number; cache_hit_rate: number;
  prompt_tokens: number; completion_tokens: number; total_tokens: number;
  saved_prompt_tokens: number; saved_completion_tokens: number; avg_latency_ms: number;
}
interface CostRow {
  model: string; input_per_million: number; output_per_million: number;
  est_cost_usd: number; saved_by_cache_usd: number;
}
interface Usage {
  stats: UsageStats; comparison: CostRow[]; local_cost_usd: number;
  feedback?: { up: number; down: number; total: number };
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
  const [usage, setUsage] = useState<Usage | null>(null);

  const refresh = useCallback(async () => {
    const [d, j, t, c, u] = await Promise.all([
      fetch("/api/dashboard/documents").then((r) => r.json()),
      fetch("/api/dashboard/jobs").then((r) => r.json()),
      fetch("/api/dashboard/tickets").then((r) => r.json()),
      fetch("/api/dashboard/chats").then((r) => r.json()),
      fetch("/api/dashboard/usage").then((r) => r.json()).catch(() => null),
    ]);
    setDocs(d.documents ?? []);
    setJobs(j.jobs ?? []);
    setTickets(t.tickets ?? []);
    setSessions(c.sessions ?? []);
    setUsage(u && !u.error ? u : null);
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
  async function setTicketStatus(id: string, status: string) {
    // Optimistic update; refresh reconciles with the server.
    setTickets((ts) => ts.map((t) => (t.id === id ? { ...t, status } : t)));
    await fetch(`/api/dashboard/tickets/${id}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ status }),
    });
    refresh();
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

      {usage && <UsagePanel usage={usage} />}

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

      <Section title={`BullMQ jobs (${filteredJobs.length})`}>
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
          headers={["email", "description", "session", "status", "actions", "created"]}
          rows={filteredTickets.map((t) => [
            t.email,
            t.description,
            t.session_id ?? "—",
            pill(t.status),
            <TicketActions key={t.id} status={t.status} onSet={(s) => setTicketStatus(t.id, s)} />,
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

const TICKET_NEXT: Record<string, string[]> = {
  open: ["in_progress", "closed"],
  in_progress: ["closed", "open"],
  closed: ["open"],
};

function TicketActions({ status, onSet }: { status: string; onSet: (s: string) => void }) {
  const next = TICKET_NEXT[status] ?? [];
  if (next.length === 0) return <>—</>;
  return (
    <span style={{ display: "flex", gap: 6 }}>
      {next.map((s) => (
        <button
          key={s}
          onClick={() => onSet(s)}
          style={{ fontSize: 12, padding: "2px 8px", cursor: "pointer" }}
          title={`set ${s}`}
        >
          → {s}
        </button>
      ))}
    </span>
  );
}

// Compact thousands formatting for token counts (12345 → "12.3k").
function fmtNum(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "k";
  return String(n);
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div style={{ flex: "1 1 130px", padding: "10px 14px", background: "#fafafa", borderRadius: 8, border: "1px solid #eee" }}>
      <div style={{ fontSize: 12, color: "#666" }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 700 }}>{value}</div>
      {sub && <div style={{ fontSize: 11, color: "#888" }}>{sub}</div>}
    </div>
  );
}

/**
 * LLM usage + cost-vs-ChatGPT panel. Shows how much the local model was used (calls,
 * tokens, latency, cache hit rate) and what the same token volume would have cost on
 * paid OpenAI models — vs Aura's actual $0 (local inference).
 */
function UsagePanel({ usage }: { usage: Usage }) {
  const s = usage.stats;
  return (
    <Section title="LLM usage & cost vs ChatGPT">
      <div style={{ display: "flex", flexWrap: "wrap", gap: 10, marginBottom: 14 }}>
        <Stat label="LLM calls" value={String(s.llm_calls)} sub={`${s.total_requests} requests total`} />
        <Stat label="Cache hits" value={String(s.cache_hits)} sub={`${Math.round(s.cache_hit_rate * 100)}% hit rate`} />
        <Stat label="Tokens (in / out)" value={`${fmtNum(s.prompt_tokens)} / ${fmtNum(s.completion_tokens)}`} sub={`${fmtNum(s.total_tokens)} total`} />
        <Stat label="Avg latency" value={`${(s.avg_latency_ms / 1000).toFixed(1)}s`} sub="per generated answer" />
        <Stat label="Aura cost" value="$0.00" sub="local inference" />
        {usage.feedback && usage.feedback.total > 0 && (
          <Stat
            label="Answer feedback"
            value={`👍 ${usage.feedback.up} / 👎 ${usage.feedback.down}`}
            sub={`${Math.round((usage.feedback.up / usage.feedback.total) * 100)}% positive`}
          />
        )}
      </div>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
        <thead>
          <tr>
            {["if run on…", "input $/1M", "output $/1M", "est. cost so far", "saved by cache"].map((h) => (
              <th key={h} style={{ textAlign: "left", padding: "4px 8px", color: "#666" }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {usage.comparison.map((c) => (
            <tr key={c.model} style={{ borderTop: "1px solid #eee" }}>
              <td style={{ padding: "6px 8px", fontWeight: 600 }}>{c.model}</td>
              <td style={{ padding: "6px 8px" }}>${c.input_per_million.toFixed(2)}</td>
              <td style={{ padding: "6px 8px" }}>${c.output_per_million.toFixed(2)}</td>
              <td style={{ padding: "6px 8px", color: "#b00020" }}>${c.est_cost_usd.toFixed(4)}</td>
              <td style={{ padding: "6px 8px", color: "#1a7f37" }}>${c.saved_by_cache_usd.toFixed(4)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p style={{ fontSize: 11, color: "#888", margin: "8px 0 0" }}>
        Estimated bill for the same tokens on OpenAI (prices configurable in <code>.env</code>).
        Aura runs the model locally, so actual spend is $0; the green column is what the
        Redis answer-cache saved by not regenerating.
      </p>
    </Section>
  );
}

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
