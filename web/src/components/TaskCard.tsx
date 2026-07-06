import type { Task } from "../types";

const STATUS_LIVE_WINDOW_MS = 30_000;

export function TaskCard({ task, fresh }: { task: Task; fresh?: boolean }) {
  const isFresh =
    fresh ??
    Date.now() - new Date(task.created_at).getTime() < STATUS_LIVE_WINDOW_MS;
  return (
    <div
      style={{
        border: "1px solid #ddd",
        borderRadius: 6,
        padding: 10,
        background: "#fff",
        boxShadow: isFresh ? "0 0 0 2px #22c55e" : "none",
      }}
    >
      <div style={{ fontWeight: 600 }}>
        #{task.id} {task.title}
      </div>
      {task.tags.length > 0 && (
        <div style={{ marginTop: 4, display: "flex", gap: 4, flexWrap: "wrap" }}>
          {task.tags.map((t) => (
            <span key={t} style={{ background: "#eee", padding: "1px 6px", borderRadius: 4, fontSize: 12 }}>
              {t}
            </span>
          ))}
        </div>
      )}
      {task.claimed_by && (
        <div style={{ marginTop: 4, fontSize: 12, color: "#666" }}>claimed by {task.claimed_by}</div>
      )}
    </div>
  );
}
