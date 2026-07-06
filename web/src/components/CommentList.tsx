import { useState } from "react";
import { api } from "../api";
import type { Comment, TaskStatus } from "../types";

type ReengageStatus = "in_progress" | "ready";

export function CommentList({
  taskId,
  comments,
  taskStatus,
  onPosted,
}: {
  taskId: number;
  comments: Comment[];
  taskStatus: TaskStatus;
  onPosted: () => void;
}) {
  const [text, setText] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Show the status selector only when the user's comment will re-engage the agent.
  const showSelector = taskStatus === "review";
  const [reengage, setReengage] = useState<ReengageStatus>("in_progress");

  async function send() {
    if (!text.trim() || pending) return;
    setPending(true);
    setError(null);
    try {
      await api.postComment(taskId, text, "user", showSelector ? reengage : undefined);
      setText("");
      onPosted();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to post comment");
    } finally {
      setPending(false);
    }
  }

  return (
    <div style={{ marginTop: 16, borderTop: "1px solid #ddd", paddingTop: 12 }}>
      <h4>Comments</h4>
      {comments.map((c) => (
        <div key={c.id} style={{ marginBottom: 8 }}>
          <div style={{ fontSize: 11, color: "#666" }}>
            {new Date(c.created_at).toLocaleString()} · <strong>{c.author}</strong>
            {c.author !== "user" && (c.seen_by_agent ? " ✓ seen" : " ⏳ not seen by agent")}
          </div>
          <div>{c.content}</div>
        </div>
      ))}
      {error && (
        <div style={{ color: "#dc2626", fontSize: 12, marginBottom: 8 }}>{error}</div>
      )}
      <div style={{ display: "flex", gap: 8, marginTop: 8, alignItems: "center" }}>
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !pending && send()}
          placeholder="Add a comment for the agent..."
          style={{ flex: 1 }}
          disabled={pending}
        />
        {showSelector && (
          <select
            value={reengage}
            onChange={(e) => setReengage(e.target.value as ReengageStatus)}
            disabled={pending}
            title="Status after posting"
          >
            <option value="in_progress">→ in_progress</option>
            <option value="ready">→ ready</option>
          </select>
        )}
        <button onClick={send} disabled={pending || !text.trim()}>
          {pending ? "Sending…" : "Send"}
        </button>
      </div>
    </div>
  );
}
