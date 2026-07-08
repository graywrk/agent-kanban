import { useEffect, useState } from "react";
import { api } from "../api";
import { LANGS, useT } from "../i18n.tsx";

export function Login({ onLoggedIn }: { onLoggedIn: () => void }) {
  const { t, locale, setLocale } = useT();
  const [mode, setMode] = useState<"login" | "setup">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .setupStatus()
      .then((s) => setMode(s.needs_setup ? "setup" : "login"))
      .catch(() => setMode("login"));
  }, []);

  async function submit() {
    setError(null);
    if (mode === "setup") {
      if (password.length < 8) {
        setError(t("login.error.shortPassword"));
        return;
      }
      if (password !== confirm) {
        setError(t("login.error.mismatch"));
        return;
      }
    }
    setBusy(true);
    try {
      if (mode === "setup") {
        await api.setup(username || "admin", password);
        await api.login(username || "admin", password);
      } else {
        await api.login(username, password);
      }
      onLoggedIn();
    } catch (e) {
      setError(e instanceof Error ? e.message : t("login.error.failed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      style={{
        minHeight: "100%",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 24,
        background:
          "radial-gradient(120% 80% at 50% 0%, var(--accent-soft) 0%, transparent 60%), var(--canvas)",
        position: "relative",
      }}
    >
      {/* Language switch — top-right corner (no header on this screen). */}
      <div
        style={{
          position: "absolute",
          top: 16,
          right: 16,
          display: "inline-flex",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius)",
          overflow: "hidden",
        }}
      >
        {LANGS.map((l) => (
          <button
            key={l.code}
            onClick={() => setLocale(l.code)}
            style={{
              padding: "4px 9px",
              minWidth: 36,
              border: "none",
              borderRadius: 0,
              background: locale === l.code ? "var(--accent)" : "transparent",
              color: locale === l.code ? "var(--accent-fg)" : "var(--text-dim)",
              fontWeight: locale === l.code ? 600 : 500,
              cursor: "pointer",
              fontFamily: "inherit",
              fontSize: "var(--text-small)",
            }}
            title={l.code === "ru" ? "Русский" : "English"}
          >
            {l.label}
          </button>
        ))}
      </div>

      <div
        className="card"
        style={{ width: "100%", maxWidth: 380, boxShadow: "var(--shadow-lg)" }}
      >
        <div className="eyebrow" style={{ marginBottom: 8 }}>
          {mode === "setup" ? t("login.eyebrow.setup") : t("login.eyebrow.login")}
        </div>
        <h1 style={{ marginBottom: 4 }}>{t("login.brand")}</h1>
        <p className="muted" style={{ marginBottom: 20, fontSize: "var(--text-small)" }}>
          {mode === "setup" ? t("login.subtitle.setup") : t("login.subtitle.login")}
        </p>

        <label className="eyebrow" style={{ display: "block", marginBottom: 6 }}>
          {t("login.usernameLabel")}
        </label>
        <input
          className="input"
          placeholder={t("login.usernamePlaceholder")}
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          style={{ marginBottom: 14 }}
          autoFocus
        />

        <label className="eyebrow" style={{ display: "block", marginBottom: 6 }}>
          {t("login.passwordLabel")}
        </label>
        <input
          className="input"
          type="password"
          placeholder="••••••••"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !busy && submit()}
          style={{ marginBottom: mode === "setup" ? 14 : 20 }}
        />

        {mode === "setup" && (
          <>
            <label className="eyebrow" style={{ display: "block", marginBottom: 6 }}>
              {t("login.confirmLabel")}
            </label>
            <input
              className="input"
              type="password"
              placeholder="••••••••"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && !busy && submit()}
              style={{ marginBottom: 20 }}
            />
          </>
        )}

        <button
          className="btn btn-primary"
          onClick={submit}
          disabled={busy}
          style={{ width: "100%" }}
        >
          {busy ? "…" : mode === "setup" ? t("login.button.setup") : t("login.button.login")}
        </button>

        {error && (
          <div
            className="badge badge-error"
            style={{ marginTop: 14, width: "100%", justifyContent: "center", padding: "6px 10px" }}
          >
            {error}
          </div>
        )}
      </div>
    </div>
  );
}
