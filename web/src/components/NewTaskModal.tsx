import { useEffect, useState } from "react";
import { api } from "../api";
import { useT } from "../i18n.tsx";
import { PRIORITY_ORDER, PRIORITY_META } from "../priorityMeta";
import type { Project, TaskPriority } from "../types";

export function NewTaskModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (t: import("../types").Task) => void;
}) {
  const { t } = useT();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [tags, setTags] = useState("");
  const [repoPath, setRepoPath] = useState("");
  const [baseBranch, setBaseBranch] = useState("");
  const [assignedTo, setAssignedTo] = useState<string>("");
  const [preferredModel, setPreferredModel] = useState<string>("");
  const [projectId, setProjectId] = useState<string>("");
  const [priority, setPriority] = useState<TaskPriority>("medium");
  const [agents, setAgents] = useState<string[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listTokens()
      .then((tokens) => setAgents([...new Set(tokens.map((tk) => tk.agent_name))].sort()))
      .catch(() => setAgents([]));
    api
      .listProjects()
      .then(setProjects)
      .catch(() => setProjects([]));
  }, []);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const tk = await api.createTask({
        title,
        description,
        tags: tags.split(",").map((s) => s.trim()).filter(Boolean),
        ...(repoPath ? { repo_path: repoPath } : {}),
        ...(baseBranch ? { base_branch: baseBranch } : {}),
        ...(assignedTo ? { assigned_to: assignedTo } : {}),
        ...(projectId ? { project_id: Number(projectId) } : {}),
        priority,
        ...(preferredModel ? { preferred_model: preferredModel } : { preferred_model: null }),
      });
      onCreated(tk);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : t("newTask.error"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        background: "var(--overlay)",
        backdropFilter: "blur(2px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 20,
        zIndex: 50,
      }}
    >
      <div
        className="card"
        onClick={(e) => e.stopPropagation()}
        style={{ width: "100%", maxWidth: 480, boxShadow: "var(--shadow-lg)", maxHeight: "90vh", overflowY: "auto" }}
      >
        <div className="eyebrow" style={{ marginBottom: 4 }}>{t("newTask.eyebrow")}</div>
        <h3 style={{ marginBottom: 16 }}>{t("newTask.title")}</h3>

        <Field label={t("newTask.titleLabel")}>
          <input
            className="input"
            placeholder={t("newTask.titlePlaceholder")}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            autoFocus
          />
        </Field>

        <Field label={t("newTask.descLabel")}>
          <textarea
            className="input"
            placeholder={t("newTask.descPlaceholder")}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={5}
            style={{ resize: "vertical", fontFamily: "var(--font-mono)" }}
          />
        </Field>

        <Field label={t("newTask.tagsLabel")}>
          <input
            className="input"
            placeholder={t("newTask.tagsPlaceholder")}
            value={tags}
            onChange={(e) => setTags(e.target.value)}
          />
        </Field>

        <Field label={t("newTask.projectLabel")}>
          <select
            className="input"
            value={projectId}
            onChange={(e) => setProjectId(e.target.value)}
          >
            <option value="">{t("newTask.projectNone")}</option>
            {projects.map((p) => (
              <option key={p.id} value={String(p.id)}>
                {p.name}
              </option>
            ))}
          </select>
        </Field>

        <Field label={t("newTask.priorityLabel")}>
          <select
            className="input"
            value={priority}
            onChange={(e) => setPriority(e.target.value as TaskPriority)}
          >
            {PRIORITY_ORDER.map((p) => (
              <option key={p} value={p}>
                {t(PRIORITY_META[p].labelKey)}
              </option>
            ))}
          </select>
        </Field>

        <Field label={t("newTask.preferredLabel")}>
          <select
            className="input mono"
            value={preferredModel}
            onChange={(e) => setPreferredModel(e.target.value)}
            title={t("newTask.preferredTooltip")}
          >
            <option value="">{t("newTask.preferredNone")}</option>
            {agents.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
        </Field>

        <Field label={t("newTask.repoLabel")}>
          <input
            className="input mono"
            placeholder="/path/to/repo"
            value={repoPath}
            onChange={(e) => setRepoPath(e.target.value)}
          />
        </Field>

        <Field label={t("newTask.baseLabel")}>
          <input
            className="input mono"
            placeholder="main"
            value={baseBranch}
            onChange={(e) => setBaseBranch(e.target.value)}
          />
        </Field>

        <Field label={t("newTask.assignLabel")}>
          <select
            className="input"
            value={assignedTo}
            onChange={(e) => setAssignedTo(e.target.value)}
            title={t("newTask.assignTooltip")}
          >
            <option value="">{t("newTask.assignAnyone")}</option>
            {agents.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
        </Field>

        {error && (
          <div className="badge badge-error" style={{ marginTop: 8, width: "100%" }}>
            {error}
          </div>
        )}

        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 20 }}>
          <button className="btn" onClick={onClose} disabled={busy}>
            {t("common.cancel")}
          </button>
          <button className="btn btn-primary" onClick={submit} disabled={!title || busy}>
            {busy ? t("newTask.creating") : t("newTask.create")}
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 12 }}>
      <label className="eyebrow" style={{ display: "block", marginBottom: 6 }}>
        {label}
      </label>
      {children}
    </div>
  );
}
