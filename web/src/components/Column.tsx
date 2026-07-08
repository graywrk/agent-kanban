import { useState } from "react";
import type { Task, TaskStatus } from "../types";
import { TaskCard } from "./TaskCard";
import { STATUS_META } from "../statusMeta";
import { useT } from "../i18n.tsx";

interface Props {
  status: TaskStatus;
  tasks: Task[];
  lastProgress: Record<number, string>;
  onDrop: (taskId: number, status: TaskStatus) => void;
  onOpen: (taskId: number) => void;
}

export function Column({ status, tasks, lastProgress, onDrop, onOpen }: Props) {
  const { t } = useT();
  const [over, setOver] = useState(false);
  const meta = STATUS_META[status];
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
        minWidth: 230,
        maxWidth: 320,
        background: "var(--surface)",
        border: `1px solid ${over ? "var(--accent)" : "var(--border)"}`,
        borderRadius: "var(--radius-lg)",
        padding: 12,
        display: "flex",
        flexDirection: "column",
        gap: 8,
        transition: "border-color var(--transition)",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 2,
        }}
      >
        <span className="eyebrow">{t(meta.labelKey)}</span>
        <span
          className="mono"
          style={{ color: "var(--text-mute)", fontSize: "var(--text-small)" }}
        >
          {tasks.length}
        </span>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {tasks.map((tk) => (
          <div
            key={tk.id}
            draggable
            onDragStart={(e) => e.dataTransfer.setData("text/plain", String(tk.id))}
            onClick={() => onOpen(tk.id)}
            style={{ cursor: "pointer" }}
          >
            <TaskCard task={tk} lastProgressAt={lastProgress[tk.id]} />
          </div>
        ))}
        {tasks.length === 0 && (
          <div
            style={{
              padding: "18px 8px",
              textAlign: "center",
              color: "var(--text-mute)",
              fontSize: "var(--text-small)",
              border: "1px dashed var(--border)",
              borderRadius: "var(--radius)",
            }}
          >
            {t("column.empty")}
          </div>
        )}
      </div>
    </div>
  );
}
