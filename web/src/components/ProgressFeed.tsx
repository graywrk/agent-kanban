import { useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import { ArtifactCard } from "./ArtifactCard";
import type { ArtifactMeta, ProgressEvent } from "../types";
import { useT, localeBcp47 } from "../i18n.tsx";

// Shiki is loaded once for the whole feed.
import type { Highlighter } from "shiki";

let highlighterPromise: Promise<Highlighter> | null = null;

async function getHighlighter(): Promise<Highlighter> {
  if (!highlighterPromise) {
    highlighterPromise = (async () => {
      const { createHighlighter } = await import("shiki");
      return createHighlighter({
        themes: ["github-light", "github-dark"],
        langs: ["diff", "typescript", "javascript", "python", "bash", "json"],
      });
    })().catch((err) => {
      highlighterPromise = null; // allow retry on next call
      throw err;
    });
  }
  return highlighterPromise;
}

const EXT_LANG: Record<string, string> = {
  ts: "typescript", tsx: "typescript", js: "javascript", jsx: "javascript",
  py: "python", sh: "bash", bash: "bash", json: "json",
};

function sourceLangLabel(content: string): string {
  // Extract the source language for DISPLAY ONLY (not the highlight grammar).
  const m = content.match(/^(?:\+\+\+ b\/|diff --git a\/)([^\n]+)/m);
  if (m) {
    const ext = m[1].split(".").pop()?.toLowerCase() ?? "";
    if (ext && EXT_LANG[ext]) return EXT_LANG[ext];
  }
  return "";
}

/** Returns "github-dark" for dark theme, "github-light" otherwise. */
function shikiTheme(): "github-dark" | "github-light" {
  return document.documentElement.dataset.theme === "light" ? "github-light" : "github-dark";
}

export function ProgressFeed({
  events,
  defaultExpanded = false,
}: {
  events: ProgressEvent[];
  defaultExpanded?: boolean;
}) {
  const { t } = useT();
  const [expandAll, setExpandAll] = useState(defaultExpanded);
  const hasDiff = events.some((e) => e.kind === "diff");
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {hasDiff && (
        <div style={{ marginBottom: 4 }}>
          <button className="btn btn-ghost btn-sm" onClick={() => setExpandAll((v) => !v)}>
            {expandAll ? t("progress.collapseAll") : t("progress.expandAll")}
          </button>
        </div>
      )}
      {events.map((e) => (
        <ProgressItem key={e.id} event={e} forceExpanded={expandAll} />
      ))}
    </div>
  );
}

function ProgressItem({
  event,
  forceExpanded,
}: {
  event: ProgressEvent;
  forceExpanded: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const effectiveExpanded = forceExpanded || expanded;
  const ts = new Date(event.created_at).toLocaleTimeString(localeBcp47());
  const content = (event.payload.content as string) || "";

  if (event.kind === "status_change") {
    return (
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          margin: "10px 0",
          color: "var(--text-mute)",
          fontSize: "var(--text-small)",
        }}
      >
        <span style={{ flex: 1, height: 1, background: "var(--border)" }} />
        <span className="mono">{content}</span>
        <span style={{ flex: 1, height: 1, background: "var(--border)" }} />
      </div>
    );
  }
  if (event.kind === "error") {
    return (
      <div
        style={{
          background: "var(--status-error-soft)",
          borderLeft: "3px solid var(--status-error)",
          padding: "8px 12px",
          borderRadius: "var(--radius)",
        }}
      >
        <div className="muted mono" style={{ fontSize: "var(--text-small)", marginBottom: 4 }}>
          {ts} · {event.agent}
        </div>
        <pre
          className="mono"
          style={{
            margin: 0,
            color: "var(--status-error)",
            whiteSpace: "pre-wrap",
            fontSize: "var(--text-mono)",
          }}
        >
          {content}
        </pre>
      </div>
    );
  }
  if (event.kind === "diff") {
    return (
      <DiffItem
        content={content}
        ts={ts}
        agent={event.agent}
        expanded={effectiveExpanded}
        onToggle={() => setExpanded((v) => !v)}
      />
    );
  }
  if (event.kind === "artifact_ref") {
    return <ArtifactTextItem ts={ts} agent={event.agent} content={content} payload={event.payload} />;
  }
  // plain text
  return (
    <div
      style={{
        background: "var(--surface)",
        border: "1px solid var(--border)",
        padding: "8px 12px",
        borderRadius: "var(--radius)",
      }}
    >
      <div className="muted mono" style={{ fontSize: "var(--text-small)", marginBottom: 4 }}>
        {ts} · <strong style={{ color: "var(--text-dim)" }}>{event.agent}</strong>
      </div>
      <div className="markdown" style={{ fontSize: "var(--text-body)", lineHeight: 1.6 }}>
        <ReactMarkdown>{content}</ReactMarkdown>
      </div>
    </div>
  );
}

function DiffItem({
  content,
  ts,
  agent,
  expanded,
  onToggle,
}: {
  content: string;
  ts: string;
  agent: string;
  expanded: boolean;
  onToggle: () => void;
}) {
  const highlightLang = "diff";
  const label = useMemo(() => sourceLangLabel(content), [content]);
  const [html, setHtml] = useState<string | null>(null);

  useEffect(() => {
    if (!expanded) return;
    let cancelled = false;
    getHighlighter()
      .then((h) => {
        if (cancelled) return;
        const out = h.codeToHtml(content, { lang: highlightLang, theme: shikiTheme() });
        setHtml(out);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [expanded, content, highlightLang]);

  const stats = content.match(/@@.*@@/g)?.length ?? 0;
  const { t, tCount } = useT();
  return (
    <div
      style={{
        background: "var(--surface)",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius)",
        overflow: "hidden",
      }}
    >
      <button
        onClick={onToggle}
        className="btn btn-ghost"
        style={{
          width: "100%",
          textAlign: "left",
          justifyContent: "flex-start",
          padding: "6px 12px",
          borderRadius: 0,
          color: "var(--text-dim)",
        }}
      >
        <span className="mono muted">{expanded ? "▼" : "▶"}</span>
        <span>{t("progress.diff")} · {ts} · {agent}</span>
        {label && <span className="muted"> · {label}</span>}
        {stats > 0 && <span className="muted"> · {tCount("progress.hunks", stats)}</span>}
      </button>
      {expanded &&
        (html ? (
          <div
            className="mono"
            style={{
              padding: 8,
              margin: 0,
              overflowX: "auto",
              fontSize: "var(--text-mono)",
              borderTop: "1px solid var(--border-soft)",
            }}
            dangerouslySetInnerHTML={{ __html: html }}
          />
        ) : (
          <pre
            className="mono"
            style={{ padding: 8, margin: 0, overflowX: "auto", fontSize: "var(--text-mono)" }}
          >
            {content}
          </pre>
        ))}
    </div>
  );
}

function ArtifactTextItem({
  ts,
  agent,
  content,
  payload,
}: {
  ts: string;
  agent: string;
  content: string;
  payload: { [k: string]: unknown };
}) {
  const artifact = (payload.artifact as ArtifactMeta | undefined) ?? {
    path: content,
    kind: "file",
  };
  return (
    <div
      style={{
        background: "var(--surface)",
        border: "1px solid var(--border)",
        padding: "8px 12px",
        borderRadius: "var(--radius)",
      }}
    >
      <div className="muted mono" style={{ fontSize: "var(--text-small)", marginBottom: 6 }}>
        {ts} · <strong style={{ color: "var(--text-dim)" }}>{agent}</strong>
      </div>
      <ArtifactCard artifact={artifact} description={content} />
    </div>
  );
}
