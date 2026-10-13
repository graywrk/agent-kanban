import type { Task } from "../types";
import { useT, localeBcp47, type Locale } from "../i18n.tsx";
import { PRIORITY_META } from "../priorityMeta";

const LIVE_WINDOW_MS = 30_000;

/** Translate a server PR status value into a display label. */
export function prStatusLabel(status: string | null | undefined, t: (k: string) => string): string {
  if (status === "merged") return t("pr.merged");
  if (status === "closed") return t("pr.closed");
  return t("pr.open");
}

/** Short created date, e.g. "12 okt" / "Oct 12". */
export function createdDate(iso: string, locale: Locale): string {
  return new Date(iso).toLocaleDateString(localeBcp47(locale), {
    month: "short",
    day: "numeric",
  });
}

export function TaskCard({
  task,
  lastProgressAt,
}: {
  task: Task;
  lastProgressAt?: string;
}) {
  const { t, locale } = useT();
  const isLive = lastProgressAt
    ? Date.now() - new Date(lastProgressAt).getTime() < LIVE_WINDOW_MS
    : false;
  const prioMeta = PRIORITY_META[task.priority];
  const showPriority = task.priority !== "medium";
  return (
    <div
      style={{
        padding: "10px 12px",
        background: "var(--elevated)",
        border: "1px solid var(--border)",
        borderLeft: isLive ? "2px solid var(--status-success)" : "1px solid var(--border)",
        borderRadius: "var(--radius)",
        transition: "border-color var(--transition), transform var(--transition)",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          gap: 6,
          marginBottom: 4,
        }}
      >
        <span
          className="mono"
          style={{ color: "var(--text-mute)", fontSize: "var(--text-small)", flexShrink: 0 }}
        >
          #{task.id}
        </span>
        <span
          className="ellipsis"
          style={{ fontWeight: 600, fontSize: "var(--text-body)", flex: 1, minWidth: 0 }}
        >
          {task.title}
        </span>
        <span
          className="mono"
          title={t("task.createdTooltip", { date: createdDate(task.created_at, locale) })}
          style={{ color: "var(--text-mute)", fontSize: "var(--text-small)", flexShrink: 0 }}
        >
          {createdDate(task.created_at, locale)}
        </span>
      </div>

      {(showPriority || task.preferred_model) && (
        <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginBottom: 4 }}>
          {showPriority && (
            <span
              className={`badge badge-${prioMeta.badge}`}
              title={t(prioMeta.labelKey)}
              style={{ padding: "1px 7px", fontSize: "var(--text-small)" }}
            >
              {t(prioMeta.labelKey)}
            </span>
          )}
          {task.preferred_model && (
            <span
              className="mono"
              title={t("task.preferredTooltip", { agent: task.preferred_model })}
              style={{
                color: "var(--text-dim)",
                background: "var(--surface)",
                border: "1px solid var(--border)",
                padding: "1px 7px",
                borderRadius: 999,
                fontSize: "var(--text-small)",
              }}
            >
              ◇ {task.preferred_model}
            </span>
          )}
        </div>
      )}

      {task.tags.length > 0 && (
        <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginBottom: 4 }}>
          {task.tags.map((tg) => (
            <span key={tg} className="tag">{tg}</span>
          ))}
        </div>
      )}

      {(task.assigned_to || task.claimed_by || task.branch || task.pr_url || isLive) && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            marginTop: 6,
            fontSize: "var(--text-small)",
            color: "var(--text-dim)",
            flexWrap: "wrap",
          }}
        >
          {task.assigned_to && (
            <span
              className="mono"
              title={t("task.reservedTooltip", { agent: task.assigned_to })}
              style={{
                color: "var(--accent-pressed)",
                background: "var(--accent-soft)",
                padding: "1px 7px",
                borderRadius: 999,
                fontSize: "var(--text-small)",
              }}
            >
              → {task.assigned_to}
            </span>
          )}
          {isLive && (
            <span style={{ display: "inline-flex", alignItems: "center", gap: 5, color: "var(--status-success)" }}>
              <span className="live-dot" />
              {t("task.live")}
            </span>
          )}
          {task.claimed_by && (
            <span className="ellipsis" style={{ maxWidth: 140 }}>
              {t("task.claimedBy", { name: task.claimed_by })}
            </span>
          )}
          {task.branch && (
            <span className="mono ellipsis" style={{ maxWidth: 140, color: "var(--text-dim)" }}>
              ⌥ {task.branch}
            </span>
          )}
          {task.pr_url && <PRBadge url={task.pr_url} status={task.pr_status} />}
        </div>
      )}
    </div>
  );
}

function PRBadge({
  url,
  status,
}: {
  url: string;
  status?: string | null;
}) {
  const { t } = useT();
  const num = url.split("/").pop() ?? "pr";
  const cls =
    status === "merged"
      ? "badge-success"
      : status === "closed"
        ? "badge-error"
        : "badge-info";
  return (
    <span className={`badge ${cls}`} style={{ padding: "1px 7px" }}>
      {t("task.pr", { num })}
      {status ? ` · ${prStatusLabel(status, t)}` : ""}
    </span>
  );
}
