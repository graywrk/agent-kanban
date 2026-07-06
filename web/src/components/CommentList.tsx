import { useState } from "react";
import { api } from "../api";
import type { Comment } from "../types";

export function CommentList({ taskId, comments, onPosted }: {
  taskId: number;
  comments: Comment[];
  onPosted: () => void;
}) {
  const [text, setText] = useState("");
  async function send() {
    if (!text.trim()) return;
    await api.postComment(taskId, text);
    setText("");
    onPosted();
  }
  return (
    <div style={{ marginTop: 16, borderTop: "1px solid #ddd", paddingTop: 12 }}>
      <h4>Comments</h4>
      {comments.map((c) => (
        <div key={c.id} style={{ marginBottom: 8 }}>
          <div style={{ fontSize: 11, color: "#666" }}>
            {new Date(c.created_at).toLocaleString()} · <strong>{c.author}</strong>
            {c.author !== "user" && (c.seen_by_agent ? " ✓ seen" : " ⏳")}
          </div>
          <div>{c.content}</div>
        </div>
      ))}
      <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder="Add a comment for the agent..."
          style={{ flex: 1 }}
        />
        <button onClick={send}>Send</button>
      </div>
    </div>
  );
}
