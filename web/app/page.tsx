"use client";

import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

// Render Aura's answers as markdown (bold specs, bullet lists) without the big default
// block margins that look wrong inside a chat bubble.
const MD_COMPONENTS = {
  p: (props: { children?: React.ReactNode }) => <p style={{ margin: "0 0 6px" }}>{props.children}</p>,
  ul: (props: { children?: React.ReactNode }) => <ul style={{ margin: "4px 0", paddingLeft: 18 }}>{props.children}</ul>,
  ol: (props: { children?: React.ReactNode }) => <ol style={{ margin: "4px 0", paddingLeft: 18 }}>{props.children}</ol>,
  li: (props: { children?: React.ReactNode }) => <li style={{ margin: "2px 0" }}>{props.children}</li>,
};

interface Doc {
  id: string;
  filename: string;
  status: string;
}

interface Msg {
  role: "user" | "aura";
  text: string;
  streaming?: boolean;
  cached?: boolean;
}

const STATUS_COLOR: Record<string, string> = {
  processing: "#b8860b",
  ready: "#1a7f37",
  failed: "#b00020",
};

export default function Home() {
  const [sessionId, setSessionId] = useState(() => crypto.randomUUID());
  const [docs, setDocs] = useState<Doc[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);

  // Live ingestion status over WebSocket.
  useEffect(() => {
    const ws = new WebSocket(`ws://${location.host}/ws`);
    ws.onmessage = (e) => {
      const evt = JSON.parse(e.data) as { type: string; documentId: string };
      if (evt.type === "kb_ready" || evt.type === "kb_failed") {
        const next = evt.type === "kb_ready" ? "ready" : "failed";
        setDocs((d) => d.map((x) => (x.id === evt.documentId ? { ...x, status: next } : x)));
      }
    };
    return () => ws.close();
  }, []);

  async function onUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch("/api/upload", { method: "POST", body: fd });
    const data = await res.json();
    if (res.ok) {
      setDocs((d) => [...d, { id: data.documentId, filename: file.name, status: "processing" }]);
    } else {
      alert(data.error ?? "upload failed");
    }
    e.target.value = "";
  }

  function toggleDoc(id: string) {
    setSelected((s) => {
      const next = new Set(s);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  function appendAura(patch: Partial<Msg>) {
    setMessages((m) => {
      const copy = [...m];
      const last = copy[copy.length - 1];
      if (last?.role === "aura" && last.streaming) {
        copy[copy.length - 1] = { ...last, ...patch, text: (patch.text ?? last.text) };
      }
      return copy;
    });
  }

  // Stream a grounded answer token-by-token over SSE.
  async function streamAnswer(query: string) {
    setMessages((m) => [...m, { role: "aura", text: "", streaming: true }]);
    const documentIds = [...selected];

    const res = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ query, documentIds, sessionId }),
    });
    if (!res.body) {
      appendAura({ text: "stream unavailable", streaming: false });
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    let acc = "";

    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });

      // Parse complete SSE frames (separated by a blank line).
      const frames = buf.split("\n\n");
      buf = frames.pop() ?? "";
      for (const frame of frames) {
        const ev = /^event: (.+)$/m.exec(frame)?.[1];
        const dataLine = /^data: (.+)$/m.exec(frame)?.[1];
        if (!dataLine) continue;
        const payload = JSON.parse(dataLine);

        if (ev === "token") {
          acc += payload.text;
          appendAura({ text: acc });
        } else if (ev === "done") {
          const cits = (payload.citations ?? []) as { document_id: string; ordinal: number }[];
          const refs = cits.length
            ? "\n\nSources: " + cits.map((c) => `doc ${c.document_id.slice(0, 8)}·#${c.ordinal}`).join(", ")
            : "";
          appendAura({ text: (payload.answer ?? acc) + refs, streaming: false, cached: payload.cached });
        } else if (ev === "error") {
          appendAura({ text: "The knowledge engine is unavailable right now.", streaming: false });
        }
      }
    }
  }

  // Start a fresh conversation: dispose the old session's server state (sticky doc
  // scope), then reset the local session id, transcript, and document selection.
  async function newChat() {
    if (busy) return;
    const old = sessionId;
    setMessages([]);
    setInput("");
    setSelected(new Set());
    setSessionId(crypto.randomUUID());
    try {
      await fetch("/api/session/reset", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ sessionId: old }),
      });
    } catch {
      // best-effort; local reset already happened
    }
  }

  async function onSend() {
    const text = input.trim();
    if (!text || busy) return;
    setMessages((m) => [...m, { role: "user", text }]);
    setInput("");
    setBusy(true);
    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ sessionId, message: text }),
      });
      const data = (await res.json()) as {
        replies?: string[];
        stream?: { query: string } | null;
        error?: string;
      };

      const replies = data.replies ?? (data.error ? [data.error] : []);
      if (replies.length) {
        setMessages((m) => [...m, ...replies.map((t) => ({ role: "aura" as const, text: t }))]);
      }
      if (data.stream) {
        await streamAnswer(data.stream.query);
      }
    } finally {
      setBusy(false);
    }
  }

  const readyDocs = docs.filter((d) => d.status === "ready");

  return (
    <main style={{ fontFamily: "system-ui", maxWidth: 760, margin: "0 auto", padding: "2rem" }}>
      <h1 style={{ marginBottom: 0 }}>Aura</h1>
      <p style={{ color: "#666", marginTop: 4 }}>
        Autonomous B2B Solutions Architect ·{" "}
        <a href="/dashboard" style={{ color: "#0969da" }}>dashboard</a>
      </p>

      <section style={{ border: "1px solid #ddd", borderRadius: 8, padding: "1rem", marginTop: "1rem" }}>
        <h2 style={{ fontSize: "1rem" }}>Knowledge base</h2>
        <input type="file" accept=".pdf,.docx,.txt,.md" onChange={onUpload} />
        <ul style={{ listStyle: "none", padding: 0 }}>
          {docs.map((d) => (
            <li key={d.id} style={{ marginTop: 6, display: "flex", alignItems: "center", gap: 8 }}>
              {d.status === "ready" && (
                <input
                  type="checkbox"
                  checked={selected.has(d.id)}
                  onChange={() => toggleDoc(d.id)}
                  title="restrict answers to this document"
                />
              )}
              <span>{d.filename}</span>
              <strong style={{ color: STATUS_COLOR[d.status] ?? "#444" }}>{d.status}</strong>
            </li>
          ))}
        </ul>
        {readyDocs.length > 0 && (
          <p style={{ color: "#666", fontSize: 13, margin: 0 }}>
            {selected.size === 0
              ? "Answering across all ready documents. Tick boxes to restrict."
              : `Answering across ${selected.size} selected document(s).`}
          </p>
        )}
      </section>

      <section style={{ border: "1px solid #ddd", borderRadius: 8, padding: "1rem", marginTop: "1rem" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <h2 style={{ fontSize: "1rem", margin: 0 }}>Chat</h2>
          <button
            onClick={newChat}
            disabled={busy}
            title="Start a new conversation and dispose the current one"
            style={{ padding: "4px 12px", fontSize: 13, cursor: "pointer" }}
          >
            + New chat
          </button>
        </div>
        <div style={{ minHeight: 200, maxHeight: 360, overflowY: "auto", margin: "8px 0" }}>
          {messages.map((m, i) => (
            <div key={i} style={{ textAlign: m.role === "user" ? "right" : "left", margin: "6px 0" }}>
              <span
                style={{
                  display: "inline-block",
                  padding: "6px 10px",
                  borderRadius: 10,
                  textAlign: "left",
                  background: m.role === "user" ? "#e7f0ff" : "#f1f1f1",
                  whiteSpace: m.role === "user" ? "pre-wrap" : "normal",
                }}
              >
                {m.role === "aura" && m.text ? (
                  <ReactMarkdown remarkPlugins={[remarkGfm]} components={MD_COMPONENTS}>
                    {m.text}
                  </ReactMarkdown>
                ) : (
                  m.text || (m.streaming ? "▍" : "")
                )}
                {m.cached && (
                  <em style={{ color: "#1a7f37", fontSize: 11, marginLeft: 6 }}>cached</em>
                )}
              </span>
            </div>
          ))}
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <input
            style={{ flex: 1, padding: 8 }}
            value={input}
            placeholder="Ask a technical question, or say 'open a ticket'…"
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && onSend()}
          />
          <button onClick={onSend} disabled={busy} style={{ padding: "8px 16px" }}>
            {busy ? "…" : "Send"}
          </button>
        </div>
      </section>
    </main>
  );
}
