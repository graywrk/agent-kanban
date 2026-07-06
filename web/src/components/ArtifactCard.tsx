import { useEffect, useState } from "react";
import type { ArtifactMeta } from "../types";

const IMAGE_KINDS = new Set(["screenshot", "image", "png", "jpg", "jpeg", "gif", "webp"]);

function iconFor(kind: string): string {
  if (IMAGE_KINDS.has(kind.toLowerCase())) return "🖼";
  if (kind.includes("log")) return "📜";
  if (kind.includes("diff") || kind.includes("patch")) return "🔧";
  return "📎";
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
  const contentUrl = artifact.id
    ? `/api/artifacts/${artifact.id}/content`
    : null;

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
        padding: 8,
        border: "1px solid #ddd",
        borderRadius: 6,
        background: "#fafafa",
        textDecoration: "none",
        color: "inherit",
        alignItems: "center",
      }}
    >
      {isImage && contentUrl ? (
        <img
          src={contentUrl}
          alt={description ?? artifact.path}
          style={{ width: 48, height: 48, objectFit: "cover", borderRadius: 4 }}
          onError={(e) => { e.currentTarget.style.display = "none"; }}
        />
      ) : (
        <span style={{ fontSize: 24 }}>{iconFor(artifact.kind)}</span>
      )}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {description ?? artifact.path.split("/").pop() ?? artifact.path}
        </div>
        <div style={{ fontSize: 11, color: "#666" }}>
          {artifact.kind}{size ? ` · ${size}` : ""}
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
