"use client";

import { useEffect, useRef, useState } from "react";

interface Doc {
  id: string;
  filename: string;
  status: string;
}

interface Msg {
  role: "user" | "aura";
  text: string;
}

const STATUS_COLOR: Record<string, string> = {
  processing: "#b8860b",
  ready: "#1a7f37",
  failed: "#b00020",
};

export default function Home() {
  const [sessionId] = useState(() => crypto.randomUUID());
  const [docs, setDocs] = useState<Doc[]>([]);
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
      const data = (await res.json()) as { replies?: string[]; error?: string };
      const replies = data.replies ?? (data.error ? [data.error] : []);
      setMessages((m) => [...m, ...replies.map((t) => ({ role: "aura" as const, text: t }))]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main style={{ fontFamily: "system-ui", maxWidth: 760, margin: "0 auto", padding: "2rem" }}>
      <h1 style={{ marginBottom: 0 }}>Aura</h1>
      <p style={{ color: "#666", marginTop: 4 }}>Autonomous B2B Solutions Architect</p>

      <section style={{ border: "1px solid #ddd", borderRadius: 8, padding: "1rem", marginTop: "1rem" }}>
        <h2 style={{ fontSize: "1rem" }}>Knowledge base</h2>
        <input type="file" accept=".pdf,.docx,.txt,.md" onChange={onUpload} />
        <ul style={{ listStyle: "none", padding: 0 }}>
          {docs.map((d) => (
            <li key={d.id} style={{ marginTop: 6 }}>
              <span>{d.filename}</span>{" "}
              <strong style={{ color: STATUS_COLOR[d.status] ?? "#444" }}>{d.status}</strong>
            </li>
          ))}
        </ul>
      </section>

      <section style={{ border: "1px solid #ddd", borderRadius: 8, padding: "1rem", marginTop: "1rem" }}>
        <h2 style={{ fontSize: "1rem" }}>Chat</h2>
        <div style={{ minHeight: 200, maxHeight: 360, overflowY: "auto", marginBottom: 8 }}>
          {messages.map((m, i) => (
            <div key={i} style={{ textAlign: m.role === "user" ? "right" : "left", margin: "6px 0" }}>
              <span
                style={{
                  display: "inline-block",
                  padding: "6px 10px",
                  borderRadius: 10,
                  background: m.role === "user" ? "#e7f0ff" : "#f1f1f1",
                  whiteSpace: "pre-wrap",
                }}
              >
                {m.text}
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
