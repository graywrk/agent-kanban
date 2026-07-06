import { useEffect, useState } from "react";
import { api, subscribeWebSocket } from "../api";
import type { Task, TaskStatus } from "../types";
import { Column } from "../components/Column";
import { NewTaskModal } from "../components/NewTaskModal";

const COLUMNS: TaskStatus[] = ["todo", "ready", "in_progress", "review", "done", "blocked", "cancelled"];

export function Board({ onOpenTask }: { onOpenTask: (id: number) => void }) {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [showNew, setShowNew] = useState(false);

  async function refresh() {
    setTasks(await api.listTasks());
  }

  useEffect(() => {
    refresh();
    const ws = subscribeWebSocket(null, () => refresh());
    return () => ws.close();
  }, []);

  async function handleDrop(taskId: number, status: TaskStatus) {
    // Optimistic.
    setTasks((prev) => prev.map((t) => (t.id === taskId ? { ...t, status } : t)));
    try {
      await api.updateTask(taskId, { status });
    } catch {
      refresh();
    }
  }

  return (
    <div style={{ padding: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <h1 style={{ margin: 0 }}>📋 Agent Kanban</h1>
        <button onClick={() => setShowNew(true)}>+ New task</button>
      </div>
      <div style={{ display: "flex", gap: 12, overflowX: "auto" }}>
        {COLUMNS.map((status) => (
          <Column
            key={status}
            status={status}
            tasks={tasks.filter((t) => t.status === status)}
            onDrop={handleDrop}
            onOpen={onOpenTask}
          />
        ))}
      </div>
      {showNew && (
        <NewTaskModal
          onClose={() => setShowNew(false)}
          onCreated={() => refresh()}
        />
      )}
      <div style={{ marginTop: 12, fontSize: 12, color: "#999" }}>
        Tip: drag cards between columns. Drop into READY to make them available to agents.
      </div>
    </div>
  );
}
