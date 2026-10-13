import { useEffect, useState } from "react";
import { api, subscribeWebSocket } from "../api";
import type { WSSubscription } from "../api";
import type { Project, Task, TaskStatus } from "../types";
import { Column } from "../components/Column";
import { NewTaskModal } from "../components/NewTaskModal";
import { useT } from "../i18n.tsx";

const COLUMNS: TaskStatus[] = ["todo", "ready", "in_progress", "review", "done", "blocked", "cancelled"];

const PROJECT_FILTER_KEY = "kanban-project-filter";

export function Board({ onOpenTask }: { onOpenTask: (id: number) => void }) {
  const { t } = useT();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectFilter, setProjectFilter] = useState<string>(
    () => localStorage.getItem(PROJECT_FILTER_KEY) ?? ""
  );
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
    api
      .listProjects()
      .then((ps) => {
        if (!cancelled) setProjects(ps);
      })
      .catch(() => {});
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

  function changeProjectFilter(value: string) {
    setProjectFilter(value);
    try {
      localStorage.setItem(PROJECT_FILTER_KEY, value);
    } catch {
      /* localStorage unavailable */
    }
  }

  async function handleDrop(taskId: number, status: TaskStatus) {
    // Optimistic.
    setTasks((prev) => prev.map((t) => (t.id === taskId ? { ...t, status } : t)));
    try {
      await api.updateTask(taskId, { status });
    } catch {
      refresh();
    }
  }

  const filterId = projectFilter === "" ? null : Number(projectFilter);
  const visibleTasks = tasks.filter((t) => filterId === null || t.project_id === filterId);

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
          <h2 style={{ margin: 0 }}>
            {filterId === null
              ? t("board.title")
              : projects.find((p) => p.id === filterId)?.name ?? t("board.title")}
          </h2>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <select
            className="input"
            value={projectFilter}
            onChange={(e) => changeProjectFilter(e.target.value)}
            title={t("board.projectFilterTooltip")}
            style={{ width: "auto" }}
          >
            <option value="">{t("board.allProjects")}</option>
            {projects.map((p) => (
              <option key={p.id} value={String(p.id)}>
                {p.name}
              </option>
            ))}
          </select>
          <button className="btn btn-primary" onClick={() => setShowNew(true)}>
            {t("board.newTask")}
          </button>
        </div>
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
            tasks={visibleTasks.filter((t) => t.status === status)}
            lastProgress={lastProgress}
            onDrop={handleDrop}
            onOpen={onOpenTask}
          />
        ))}
      </div>
      {showNew && <NewTaskModal onClose={() => setShowNew(false)} onCreated={() => refresh()} />}
      <p className="mute2" style={{ marginTop: 14, fontSize: "var(--text-small)" }}>
        {t("board.tip", { ready: t("board.tipReady") })}
      </p>
    </div>
  );
}
