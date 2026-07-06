import { useState } from "react";
import ReactMarkdown from "react-markdown";
import type { ProgressEvent } from "../types";

export function ProgressFeed({ events }: { events: ProgressEvent[] }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {events.map((e) => (
        <ProgressItem key={e.id} event={e} />
      ))}
    </div>
  );
}

function ProgressItem({ event }: { event: ProgressEvent }) {
  const [expanded, setExpanded] = useState(false);
  const ts = new Date(event.created_at).toLocaleTimeString();
  const content = (event.payload.content as string) || "";

  if (event.kind === "status_change") {
    return (
      <div style={{ borderTop: "1px dashed #aaa", margin: "8px 0", paddingTop: 4, fontSize: 12, color: "#666", textAlign: "center" }}>
        ── {content} ──
      </div>
    );
  }
  if (event.kind === "error") {
    return (
      <div style={{ background: "#fee2e2", borderLeft: "3px solid #ef4444", padding: 8, borderRadius: 4 }}>
        <div style={{ fontSize: 11, color: "#666", marginBottom: 4 }}>{ts} · {event.agent}</div>
        <div style={{ fontFamily: "monospace", color: "#991b1b" }}>{content}</div>
      </div>
    );
  }
  if (event.kind === "diff") {
    return (
      <div style={{ background: "#f8f8f8", border: "1px solid #ddd", borderRadius: 4 }}>
        <button onClick={() => setExpanded(!expanded)} style={{ width: "100%", textAlign: "left", padding: 6, background: "none", border: "none", cursor: "pointer" }}>
          {expanded ? "▼" : "▶"} diff · {ts} · {event.agent}
        </button>
        {expanded && (
          <pre style={{ padding: 8, margin: 0, overflowX: "auto", fontSize: 12 }}>{content}</pre>
        )}
      </div>
    );
  }
  // text or artifact_ref
  return (
    <div style={{ background: "#fff", border: "1px solid #eee", padding: 8, borderRadius: 4 }}>
      <div style={{ fontSize: 11, color: "#666", marginBottom: 4 }}>
        {ts} · <strong>{event.agent}</strong>
        {event.kind === "artifact_ref" && " · 📎 artifact"}
      </div>
      <div style={{ fontSize: 14 }}>
        <ReactMarkdown>{content}</ReactMarkdown>
      </div>
    </div>
  );
}
