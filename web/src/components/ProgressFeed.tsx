import { useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import { ArtifactCard } from "./ArtifactCard";
import type { ArtifactMeta, ProgressEvent } from "../types";

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
      highlighterPromise = null;  // allow retry on next call
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

export function ProgressFeed({
  events,
  defaultExpanded = false,
}: {
  events: ProgressEvent[];
  defaultExpanded?: boolean;
}) {
  const [expandAll, setExpandAll] = useState(defaultExpanded);
  const hasDiff = events.some((e) => e.kind === "diff");
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {hasDiff && (
        <div style={{ marginBottom: 4 }}>
          <button onClick={() => setExpandAll((v) => !v)}>
            {expandAll ? "Collapse all diffs" : "Expand all diffs"}
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
  const ts = new Date(event.created_at).toLocaleTimeString();
  const content = (event.payload.content as string) || "";

  if (event.kind === "status_change") {
    return (
      <div style={{ borderTop: "1px dashed #aaa", margin: "8px 0", paddingTop: 4, fontSize: 12, color: "#666", textAlign: "center" }}>
        ── {content} ──
      </div>
    );
  }
  if (event.kind === "error") {
    return (
      <div style={{ background: "#fee2e2", borderLeft: "3px solid #ef4444", padding: 8, borderRadius: 4 }}>
        <div style={{ fontSize: 11, color: "#666", marginBottom: 4 }}>{ts} · {event.agent}</div>
        <pre style={{ margin: 0, fontFamily: "monospace", color: "#991b1b", whiteSpace: "pre-wrap" }}>{content}</pre>
      </div>
    );
  }
  if (event.kind === "diff") {
    return <DiffItem content={content} ts={ts} agent={event.agent} expanded={effectiveExpanded} onToggle={() => setExpanded((v) => !v)} />;
  }
  if (event.kind === "artifact_ref") {
    return <ArtifactTextItem ts={ts} agent={event.agent} content={content} payload={event.payload} />;
  }
  // plain text
  return (
    <div style={{ background: "#fff", border: "1px solid #eee", padding: 8, borderRadius: 4 }}>
      <div style={{ fontSize: 11, color: "#666", marginBottom: 4 }}>{ts} · <strong>{event.agent}</strong></div>
      <div style={{ fontSize: 14 }}>
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
    getHighlighter().then((h) => {
      if (cancelled) return;
      const out = h.codeToHtml(content, { lang: highlightLang, theme: "github-light" });
      setHtml(out);
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [expanded, content, highlightLang]);

  const stats = content.match(/@@.*@@/g)?.length ?? 0;
  return (
    <div style={{ background: "#f8f8f8", border: "1px solid #ddd", borderRadius: 4 }}>
      <button
        onClick={onToggle}
        style={{ width: "100%", textAlign: "left", padding: 6, background: "none", border: "none", cursor: "pointer" }}
      >
        {expanded ? "▼" : "▶"} diff · {ts} · {agent}{label ? ` · ${label}` : ""}{stats > 0 ? ` · ${stats} hunk(s)` : ""}
      </button>
      {expanded && (
        html ? (
          <div
            style={{ padding: 8, margin: 0, overflowX: "auto", fontSize: 12 }}
            dangerouslySetInnerHTML={{ __html: html }}
          />
        ) : (
          <pre style={{ padding: 8, margin: 0, overflowX: "auto", fontSize: 12 }}>{content}</pre>
        )
      )}
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
  const artifact = (payload.artifact as ArtifactMeta | undefined) ?? { path: content, kind: "file" };
  return (
    <div style={{ background: "#fff", border: "1px solid #eee", padding: 8, borderRadius: 4 }}>
      <div style={{ fontSize: 11, color: "#666", marginBottom: 4 }}>
        {ts} · <strong>{agent}</strong>
      </div>
      <ArtifactCard artifact={artifact} description={content} />
    </div>
  );
}
