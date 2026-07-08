import { useEffect, useState } from "react";
import { api, subscribeWebSocket } from "../api";
import type { WSSubscription } from "../api";
import type { Task, TaskStatus } from "../types";
import { Column } from "../components/Column";
import { NewTaskModal } from "../components/NewTaskModal";
import { useT } from "../i18n.tsx";

const COLUMNS: TaskStatus[] = ["todo", "ready", "in_progress", "review", "done", "blocked", "cancelled"];

export function Board({ onOpenTask }: { onOpenTask: (id: number) => void }) {
  const { t, locale } = useT();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [lastProgress, setLastProgress] = useState<Record<number, string>>({});
  const [showNew, setShowNew] = useState(false);
  const [, setTick] = useState(0);

  async function refresh() {
    const [tasks, lp] = await Promise.all([
      api.listTasks(),
      api.listLastProgressTimestamps(),
    ]);
    setTasks(tasks);
    setLastProgress(lp);
  }

  useEffect(() => {
    let sub: WSSubscription | null = null;
    let cancelled = false;
    refresh();
    subscribeWebSocket(null, () => refresh()).then((s) => {
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
  }, []);

  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 5000);
    return () => clearInterval(id);
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
    <div style={{ padding: "20px 20px 24px", display: "flex", flexDirection: "column", minHeight: "100%" }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 16,
          gap: 12,
        }}
      >
        <div>
          <div className="eyebrow" style={{ marginBottom: 2 }}>{t("board.eyebrow")}</div>
          <h2 style={{ margin: 0 }}>{t("board.title")}</h2>
        </div>
        <button className="btn btn-primary" onClick={() => setShowNew(true)}>
          {t("board.newTask")}
        </button>
      </div>
      <div
        style={{
          display: "flex",
          gap: 12,
          overflowX: "auto",
          paddingBottom: 4,
          flex: 1,
          minHeight: 0,
        }}
      >
        {COLUMNS.map((status) => (
          <Column
            key={status}
            status={status}
            tasks={tasks.filter((t) => t.status === status)}
            lastProgress={lastProgress}
            onDrop={handleDrop}
            onOpen={onOpenTask}
          />
        ))}
      </div>
      {showNew && <NewTaskModal onClose={() => setShowNew(false)} onCreated={() => refresh()} />}
      <p className="mute2" style={{ marginTop: 14, fontSize: "var(--text-small)" }}>
        {/* The tip embeds the column name "READY"; render inline so the word
            stays bold regardless of locale. Translations split around it. */}
        {locale === "ru" ? (
          <>
            Перетаскивайте карточки между колонками. Бросьте в{" "}
            <strong style={{ color: "var(--text-dim)" }}>READY</strong>, чтобы сделать их
            доступными агентам через MCP.
          </>
        ) : (
          <>
            Drag cards between columns. Drop into{" "}
            <strong style={{ color: "var(--text-dim)" }}>READY</strong> to make them
            available to agents via MCP.
          </>
        )}
      </p>
    </div>
  );
}
