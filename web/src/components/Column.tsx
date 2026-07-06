import { useState } from "react";
import type { Task, TaskStatus } from "../types";
import { TaskCard } from "./TaskCard";

interface Props {
  status: TaskStatus;
  tasks: Task[];
  lastProgress: Record<number, string>;
  onDrop: (taskId: number, status: TaskStatus) => void;
  onOpen: (taskId: number) => void;
}

const LABELS: Record<TaskStatus, string> = {
  todo: "TODO",
  ready: "READY",
  in_progress: "ACTIVE",
  review: "REVIEW",
  done: "DONE",
  blocked: "BLOCKED",
  cancelled: "CANCELLED",
};

export function Column({ status, tasks, lastProgress, onDrop, onOpen }: Props) {
  const [over, setOver] = useState(false);
  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        const taskId = Number(e.dataTransfer.getData("text/plain"));
        onDrop(taskId, status);
      }}
      style={{
        flex: "1 1 0",
        minWidth: 220,
        background: over ? "#f0fdf4" : "#f7f7f7",
        borderRadius: 8,
        padding: 10,
        display: "flex",
        flexDirection: "column",
        gap: 8,
      }}
    >
      <div style={{ fontWeight: 700, textTransform: "uppercase", fontSize: 13, letterSpacing: 1 }}>
        {LABELS[status]} ({tasks.length})
      </div>
      {tasks.map((t) => (
        <div
          key={t.id}
          draggable
          onDragStart={(e) => e.dataTransfer.setData("text/plain", String(t.id))}
          onClick={() => onOpen(t.id)}
          style={{ cursor: "pointer" }}
        >
          <TaskCard task={t} lastProgressAt={lastProgress[t.id]} />
        </div>
      ))}
    </div>
  );
}
