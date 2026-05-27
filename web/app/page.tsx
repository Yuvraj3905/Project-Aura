export default function Home() {
  return (
    <main style={{ fontFamily: "system-ui", padding: "2rem", maxWidth: 720 }}>
      <h1>Aura</h1>
      <p>Autonomous B2B Solutions Architect.</p>
      <p style={{ color: "#666" }}>
        Upload + chat UI lands in a later phase. API: <code>POST /api/upload</code>,{" "}
        <code>GET /api/documents/:id</code>; WebSocket at <code>/ws</code>.
      </p>
    </main>
  );
}
