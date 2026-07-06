import { useEffect, useState } from "react";
import { api, subscribeWebSocket } from "../api";
import type { WSSubscription } from "../api";
import type { Comment, ProgressEvent, Task } from "../types";
import { ProgressFeed } from "../components/ProgressFeed";
import { CommentList } from "../components/CommentList";

export function CardDetail({ taskId, onBack }: { taskId: number; onBack: () => void }) {
  const [task, setTask] = useState<Task | null>(null);
  const [progress, setProgress] = useState<ProgressEvent[]>([]);
  const [comments, setComments] = useState<Comment[]>([]);
  const [actionError, setActionError] = useState<string | null>(null);

  async function refresh() {
    setTask(await api.getTask(taskId));
    setProgress(await api.listProgress(taskId));
    setComments(await api.listComments(taskId));
  }

  useEffect(() => {
    let sub: WSSubscription | null = null;
    let cancelled = false;
    refresh();
    subscribeWebSocket(taskId, () => refresh()).then((s) => {
      if (cancelled) {
        s.close();
      } else {
        sub = s;
      }
    });
    return () => {
      cancelled = true;
      sub?.close();
    };
  }, [taskId]);

  if (!task) return <div>Loading…</div>;

  return (
    <div style={{ padding: 16 }}>
      <button onClick={onBack}>← Back</button>
      <h2>#{task.id}: {task.title}</h2>
      <div style={{ color: "#666", marginBottom: 12 }}>
        status: <strong>{task.status}</strong>
        {task.claimed_by && <> · claimed by {task.claimed_by}</>}
        {task.branch && <> · ⎇ <code>{task.branch}</code></>}
        {task.pr_url && (
          <>
            {" · "}PR{" "}
            <a href={task.pr_url} target="_blank" rel="noreferrer">
              #{task.pr_url.split("/").pop()}
            </a>{" "}
            <em
              style={{
                color:
                  task.pr_status === "merged" ? "#166534"
                  : task.pr_status === "closed" ? "#991b1b"
                  : "#1e40af",
              }}
            >
              ({task.pr_status ?? "open"})
            </em>
          </>
        )}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 16 }}>
        <div>
          <h4>Progress</h4>
          <ProgressFeed events={progress} />
          <CommentList taskId={taskId} comments={comments} taskStatus={task.status} onPosted={refresh} />
        </div>
        <div>
          <h4>Details</h4>
          <div style={{ background: "#f7f7f7", padding: 12, borderRadius: 6, fontSize: 14 }}>
            {task.description || <em>No description</em>}
          </div>
          <div style={{ marginTop: 12 }}>
            {actionError && (
              <div style={{ color: "#dc2626", fontSize: 12, marginBottom: 8 }}>{actionError}</div>
            )}
            <button
              onClick={async () => {
                setActionError(null);
                try {
                  await api.updateTask(taskId, { status: "ready" });
                  refresh();
                } catch (e) {
                  setActionError(e instanceof Error ? e.message : "Failed to update task");
                }
              }}
            >
              Reopen → ready
            </button>{" "}
            <button
              onClick={async () => {
                setActionError(null);
                try {
                  await api.updateTask(taskId, { status: "cancelled" });
                  refresh();
                } catch (e) {
                  setActionError(e instanceof Error ? e.message : "Failed to update task");
                }
              }}
            >
              Cancel
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
