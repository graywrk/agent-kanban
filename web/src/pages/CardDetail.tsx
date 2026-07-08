import { useEffect, useState } from "react";
import { api, subscribeWebSocket } from "../api";
import type { WSSubscription } from "../api";
import type { Comment, ProgressEvent, Task } from "../types";
import { ProgressFeed } from "../components/ProgressFeed";
import { CommentList } from "../components/CommentList";
import { STATUS_META } from "../statusMeta";
import { useT } from "../i18n.tsx";
import { prStatusLabel } from "../components/TaskCard";

export function CardDetail({ taskId, onBack }: { taskId: number; onBack: () => void }) {
  const { t } = useT();
  const [task, setTask] = useState<Task | null>(null);
  const [progress, setProgress] = useState<ProgressEvent[]>([]);
  const [comments, setComments] = useState<Comment[]>([]);
  const [actionError, setActionError] = useState<string | null>(null);
  const [agents, setAgents] = useState<string[]>([]);

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

  // Load agent names (from tokens) once for the assign selector.
  useEffect(() => {
    api
      .listTokens()
      .then((tokens) => setAgents([...new Set(tokens.map((tk) => tk.agent_name))].sort()))
      .catch(() => setAgents([]));
  }, []);

  if (!task) {
    return (
      <div style={{ padding: 40, color: "var(--text-mute)", textAlign: "center" }}>
        {t("common.loading")}
      </div>
    );
  }

  const meta = STATUS_META[task.status];

  return (
    <div style={{ padding: "20px 20px 32px", maxWidth: 1100, margin: "0 auto" }}>
      <button className="btn btn-ghost btn-sm" onClick={onBack} style={{ marginBottom: 16 }}>
        {t("card.back")}
      </button>

      <div className="eyebrow" style={{ marginBottom: 4 }}>{t("card.taskPrefix", { id: String(task.id) })}</div>
      <h1 style={{ marginBottom: 14 }}>{task.title}</h1>

      <div
        style={{
          display: "flex",
          gap: 10,
          flexWrap: "wrap",
          alignItems: "center",
          marginBottom: 20,
        }}
      >
        <span className={`badge badge-${meta.badge}`}>
          <span className="badge-dot" />
          {t(meta.labelKey)}
        </span>
        {task.assigned_to && (
          <span
            className="mono"
            title={t("card.reservedTooltip")}
            style={{
              fontSize: "var(--text-small)",
              color: "var(--accent-pressed)",
              background: "var(--accent-soft)",
              padding: "1px 8px",
              borderRadius: 999,
            }}
          >
            → {task.assigned_to}
          </span>
        )}
        {task.claimed_by && (
          <span className="muted" style={{ fontSize: "var(--text-small)" }}>
            {t("task.claimedBy", { name: task.claimed_by })}
          </span>
        )}
        {task.branch && (
          <span className="mono" style={{ fontSize: "var(--text-small)" }}>
            ⌥ {task.branch}
          </span>
        )}
        {task.pr_url && (
          <a
            href={task.pr_url}
            target="_blank"
            rel="noreferrer"
            className="mono"
            style={{ fontSize: "var(--text-small)" }}
          >
            {t("task.pr", { num: String(task.pr_url.split("/").pop()) })}
            {task.pr_status ? ` · ${prStatusLabel(task.pr_status, t)}` : ""}
          </a>
        )}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 2fr) minmax(280px, 1fr)", gap: 20 }}>
        <div style={{ minWidth: 0 }}>
          <h4 style={{ marginBottom: 10 }}>{t("card.section.progress")}</h4>
          <ProgressFeed events={progress} />
          <CommentList taskId={taskId} comments={comments} taskStatus={task.status} onPosted={refresh} />
        </div>
        <div>
          <h4 style={{ marginBottom: 10 }}>{t("card.section.details")}</h4>
          <div
            style={{
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius)",
              padding: 14,
              fontSize: "var(--text-body)",
              lineHeight: 1.6,
            }}
          >
            {task.description || <span className="muted">{t("card.noDescription")}</span>}
          </div>

          {task.tags.length > 0 && (
            <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginTop: 12 }}>
              {task.tags.map((tg) => (
                <span key={tg} className="tag">{tg}</span>
              ))}
            </div>
          )}

          {/* Assignment control — operator reserves the task for one agent. */}
          <div style={{ marginTop: 16 }}>
            <label className="eyebrow" style={{ display: "block", marginBottom: 6 }}>
              {t("card.assignedTo")}
            </label>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <select
                className="input mono"
                value={task.assigned_to ?? ""}
                onChange={async (e) => {
                  setActionError(null);
                  try {
                    await api.updateTask(taskId, {
                      assigned_to: e.target.value || null,
                    });
                    refresh();
                  } catch (err) {
                    setActionError(
                      err instanceof Error ? err.message : t("card.error.assign")
                    );
                  }
                }}
                title={t("card.assignTooltip")}
                style={{ width: "auto", flex: 1 }}
              >
                <option value="">{t("card.assignAnyone")}</option>
                {agents.map((a) => (
                  <option key={a} value={a}>
                    {a}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div style={{ marginTop: 16 }}>
            {actionError && (
              <div className="badge badge-error" style={{ marginBottom: 8, width: "100%" }}>
                {actionError}
              </div>
            )}
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <button
                className="btn"
                onClick={async () => {
                  setActionError(null);
                  try {
                    await api.updateTask(taskId, { status: "ready" });
                    refresh();
                  } catch (e) {
                    setActionError(e instanceof Error ? e.message : t("card.error.update"));
                  }
                }}
              >
                {t("card.reopenReady")}
              </button>
              <button
                className="btn btn-danger"
                onClick={async () => {
                  setActionError(null);
                  try {
                    await api.updateTask(taskId, { status: "cancelled" });
                    refresh();
                  } catch (e) {
                    setActionError(e instanceof Error ? e.message : t("card.error.update"));
                  }
                }}
              >
                {t("card.cancel")}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
