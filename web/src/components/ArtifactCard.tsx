import { useEffect, useState } from "react";
import type { ArtifactMeta } from "../types";

const IMAGE_KINDS = new Set(["screenshot", "image", "png", "jpg", "jpeg", "gif", "webp"]);

function iconFor(kind: string): string {
  if (IMAGE_KINDS.has(kind.toLowerCase())) return "IMG";
  if (kind.includes("log")) return "LOG";
  if (kind.includes("diff") || kind.includes("patch")) return "DIFF";
  return "FILE";
}

export function ArtifactCard({
  artifact,
  description,
}: {
  artifact: ArtifactMeta;
  description?: string;
}) {
  const [size, setSize] = useState<string | null>(null);
  const isImage = IMAGE_KINDS.has(artifact.kind.toLowerCase());
  const contentUrl = artifact.id ? `/api/artifacts/${artifact.id}/content` : null;

  useEffect(() => {
    if (!contentUrl) return;
    fetch(contentUrl, { method: "HEAD" })
      .then((r) => {
        const len = r.headers.get("content-length");
        if (len) setSize(formatBytes(Number(len)));
      })
      .catch(() => {});
  }, [contentUrl]);

  return (
    <a
      href={contentUrl ?? `file:///${artifact.path}`}
      onClick={contentUrl ? undefined : (e) => e.preventDefault()}
      title={artifact.path}
      style={{
        display: "flex",
        gap: 10,
        padding: "8px 10px",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius)",
        background: "var(--elevated)",
        textDecoration: "none",
        color: "inherit",
        alignItems: "center",
        transition: "border-color var(--transition)",
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = "var(--accent)";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = "var(--border)";
      }}
    >
      {isImage && contentUrl ? (
        <img
          src={contentUrl}
          alt={description ?? artifact.path}
          style={{ width: 40, height: 40, objectFit: "cover", borderRadius: "var(--radius-sm)" }}
          onError={(e) => {
            e.currentTarget.style.display = "none";
          }}
        />
      ) : (
        <span
          className="mono"
          style={{
            fontSize: "var(--text-eyebrow)",
            fontWeight: 600,
            letterSpacing: "0.05em",
            color: "var(--text-mute)",
            background: "var(--canvas)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-sm)",
            padding: "5px 6px",
            flexShrink: 0,
          }}
        >
          {iconFor(artifact.kind)}
        </span>
      )}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="ellipsis" style={{ fontWeight: 500 }}>
          {description ?? artifact.path.split("/").pop() ?? artifact.path}
        </div>
        <div className="mono muted" style={{ fontSize: "var(--text-small)" }}>
          {artifact.kind}
          {size ? ` · ${size}` : ""}
        </div>
      </div>
    </a>
  );
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
