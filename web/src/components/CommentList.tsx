import { useState } from "react";
import ReactMarkdown from "react-markdown";
import { api } from "../api";
import type { Comment, TaskStatus } from "../types";
import { useT, localeBcp47 } from "../i18n.tsx";

type ReengageStatus = "in_progress" | "ready";

export function CommentList({
  taskId,
  comments,
  taskStatus,
  onPosted,
}: {
  taskId: number;
  comments: Comment[];
  taskStatus: TaskStatus;
  onPosted: () => void;
}) {
  const { t, locale } = useT();
  const [text, setText] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const showSelector = taskStatus === "review";
  const [reengage, setReengage] = useState<ReengageStatus>("in_progress");

  async function send() {
    if (!text.trim() || pending) return;
    setPending(true);
    setError(null);
    try {
      await api.postComment(taskId, text, "user", showSelector ? reengage : undefined);
      setText("");
      onPosted();
    } catch (e) {
      setError(e instanceof Error ? e.message : t("comment.error"));
    } finally {
      setPending(false);
    }
  }

  return (
    <div style={{ marginTop: 20, paddingTop: 16, borderTop: "1px solid var(--border)" }}>
      <h4 style={{ marginBottom: 10 }}>{t("comment.heading")}</h4>
      {comments.length === 0 && (
        <p className="mute2" style={{ fontSize: "var(--text-small)", marginBottom: 12 }}>
          {t("comment.empty")}
        </p>
      )}
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {comments.map((c) => (
          <div
            key={c.id}
            style={{
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius)",
              padding: "8px 12px",
            }}
          >
            <div
              className="mono muted"
              style={{
                fontSize: "var(--text-small)",
                marginBottom: 4,
                display: "flex",
                alignItems: "center",
                gap: 8,
                flexWrap: "wrap",
              }}
            >
              <span>{new Date(c.created_at).toLocaleString(localeBcp47(locale))}</span>
              <span style={{ color: "var(--text-dim)" }}>·</span>
              <strong style={{ color: "var(--text-dim)" }}>{c.author}</strong>
              {c.author !== "user" &&
                (c.seen_by_agent ? (
                  <span className="badge badge-success" style={{ padding: "1px 6px" }}>
                    {t("comment.seen")}
                  </span>
                ) : (
                  <span className="badge badge-neutral" style={{ padding: "1px 6px" }}>
                    {t("comment.pending")}
                  </span>
                ))}
            </div>
            <div className="markdown" style={{ fontSize: "var(--text-body)", lineHeight: 1.55 }}>
              <ReactMarkdown>{c.content}</ReactMarkdown>
            </div>
          </div>
        ))}
      </div>

      {error && (
        <div className="badge badge-error" style={{ marginTop: 8 }}>
          {error}
        </div>
      )}

      <div style={{ display: "flex", gap: 8, marginTop: 12, alignItems: "center" }}>
        <input
          className="input"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !pending && send()}
          placeholder={t("comment.inputPlaceholder")}
          disabled={pending}
        />
        {showSelector && (
          <select
            className="input"
            value={reengage}
            onChange={(e) => setReengage(e.target.value as ReengageStatus)}
            disabled={pending}
            title={t("comment.statusAfter")}
            style={{ width: "auto", flex: "0 0 auto" }}
          >
            <option value="in_progress">{t("comment.toInProgress")}</option>
            <option value="ready">{t("comment.toReady")}</option>
          </select>
        )}
        <button className="btn btn-primary" onClick={send} disabled={pending || !text.trim()}>
          {pending ? t("comment.sending") : t("common.send")}
        </button>
      </div>
    </div>
  );
}
