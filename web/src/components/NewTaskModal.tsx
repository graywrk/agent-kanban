import { useState } from "react";
import { api } from "../api";
import type { Task } from "../types";

export function NewTaskModal({ onClose, onCreated }: { onClose: () => void; onCreated: (t: Task) => void }) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [tags, setTags] = useState("");
  const [repoPath, setRepoPath] = useState("");
  const [baseBranch, setBaseBranch] = useState("");

  async function submit() {
    const t = await api.createTask({
      title,
      description,
      tags: tags.split(",").map((s) => s.trim()).filter(Boolean),
      ...(repoPath ? { repo_path: repoPath } : {}),
      ...(baseBranch ? { base_branch: baseBranch } : {}),
    });
    onCreated(t);
    onClose();
  }

  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.4)", display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div onClick={(e) => e.stopPropagation()} style={{ background: "#fff", padding: 20, borderRadius: 8, minWidth: 400 }}>
        <h3>New task</h3>
        <input placeholder="Title" value={title} onChange={(e) => setTitle(e.target.value)} style={{ width: "100%", marginBottom: 8 }} />
        <textarea placeholder="Description (markdown)" value={description} onChange={(e) => setDescription(e.target.value)} rows={5} style={{ width: "100%", marginBottom: 8 }} />
        <input placeholder="Tags (comma-separated)" value={tags} onChange={(e) => setTags(e.target.value)} style={{ width: "100%", marginBottom: 8 }} />
        <input
          placeholder="Repo path (optional, for coding tasks)"
          value={repoPath}
          onChange={(e) => setRepoPath(e.target.value)}
          style={{ width: "100%", marginBottom: 8 }}
        />
        <input
          placeholder="Base branch (optional, e.g. main)"
          value={baseBranch}
          onChange={(e) => setBaseBranch(e.target.value)}
          style={{ width: "100%", marginBottom: 12 }}
        />
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button onClick={onClose}>Cancel</button>
          <button onClick={submit} disabled={!title}>Create</button>
        </div>
      </div>
    </div>
  );
}
