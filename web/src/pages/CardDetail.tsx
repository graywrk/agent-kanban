import { useEffect, useState } from "react";
import { api, subscribeWebSocket } from "../api";
import type { Comment, ProgressEvent, Task } from "../types";
import { ProgressFeed } from "../components/ProgressFeed";
import { CommentList } from "../components/CommentList";

export function CardDetail({ taskId, onBack }: { taskId: number; onBack: () => void }) {
  const [task, setTask] = useState<Task | null>(null);
  const [progress, setProgress] = useState<ProgressEvent[]>([]);
  const [comments, setComments] = useState<Comment[]>([]);

  async function refresh() {
    setTask(await api.getTask(taskId));
    setProgress(await api.listProgress(taskId));
    setComments(await api.listComments(taskId));
  }

  useEffect(() => {
    refresh();
    const ws = subscribeWebSocket(taskId, () => refresh());
    return () => ws.close();
  }, [taskId]);

  if (!task) return <div>Loading…</div>;

  return (
    <div style={{ padding: 16 }}>
      <button onClick={onBack}>← Back</button>
      <h2>#{task.id}: {task.title}</h2>
      <div style={{ color: "#666", marginBottom: 12 }}>
        status: <strong>{task.status}</strong>
        {task.claimed_by && <> · claimed by {task.claimed_by}</>}
        {task.branch && <> · branch: {task.branch}</>}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 16 }}>
        <div>
          <h4>Progress</h4>
          <ProgressFeed events={progress} />
          <CommentList taskId={taskId} comments={comments} onPosted={refresh} />
        </div>
        <div>
          <h4>Details</h4>
          <div style={{ background: "#f7f7f7", padding: 12, borderRadius: 6, fontSize: 14 }}>
            {task.description || <em>No description</em>}
          </div>
          <div style={{ marginTop: 12 }}>
            <button onClick={() => api.updateTask(taskId, { status: "ready" }).then(refresh)}>
              Reopen → ready
            </button>{" "}
            <button onClick={() => api.updateTask(taskId, { status: "cancelled" }).then(refresh)}>
              Cancel
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
