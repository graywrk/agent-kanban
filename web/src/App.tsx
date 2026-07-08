import { useEffect, useState } from "react";
import { api } from "./api";
import { Login } from "./pages/Login";
import { Admin } from "./pages/Admin";
import { Board } from "./pages/Board";
import { CardDetail } from "./pages/CardDetail";
import { getStoredTheme, setTheme, toggleTheme, type Theme } from "./theme";
import { LANGS, useT } from "./i18n.tsx";

type View =
  | { name: "loading" }
  | { name: "login" }
  | { name: "board" }
  | { name: "admin" }
  | { name: "card"; taskId: number };

export default function App() {
  const [view, setView] = useState<View>({ name: "loading" });
  const [me, setMe] = useState<{ is_admin: boolean } | null>(null);

  async function recheck() {
    try {
      const m = await api.me();
      setMe(m);
      setView({ name: "board" });
    } catch {
      setMe(null);
      setView({ name: "login" });
    }
  }

  useEffect(() => {
    // Apply persisted theme on boot (index.html defaults to dark).
    const stored = getStoredTheme();
    if (stored) setTheme(stored);

    recheck();
    const onUnauthorized = () => {
      setMe(null);
      setView({ name: "login" });
    };
    window.addEventListener("kanban:unauthorized", onUnauthorized);
    return () => window.removeEventListener("kanban:unauthorized", onUnauthorized);
  }, []);

  if (view.name === "loading") {
    return (
      <div style={{ padding: 40, color: "var(--text-mute)", textAlign: "center" }}>
        Loading…
      </div>
    );
  }
  if (view.name === "login") return <Login onLoggedIn={recheck} />;
  if (view.name === "admin")
    return (
      <Shell me={me}>
        <Admin onBack={() => setView({ name: "board" })} />
      </Shell>
    );
  if (view.name === "card")
    return (
      <Shell me={me}>
        <CardDetail taskId={view.taskId} onBack={() => setView({ name: "board" })} />
      </Shell>
    );

  return (
    <Shell me={me} onAdmin={() => setView({ name: "admin" })}>
      <Board onOpenTask={(id) => setView({ name: "card", taskId: id })} />
    </Shell>
  );
}

/** App chrome: sticky header with the board wordmark, theme/lang toggle, admin, logout. */
function Shell({
  me,
  onAdmin,
  children,
}: {
  me: { is_admin: boolean } | null;
  onAdmin?: () => void;
  children: React.ReactNode;
}) {
  const [theme, setThemeState] = useState<Theme>(() => getStoredTheme() ?? "dark");
  const { t, locale, setLocale } = useT();

  function onToggleTheme() {
    const next = toggleTheme();
    setThemeState(next);
  }

  async function logout() {
    await api.logout();
    location.reload();
  }

  return (
    <div style={{ minHeight: "100%", display: "flex", flexDirection: "column" }}>
      <header
        style={{
          position: "sticky",
          top: 0,
          zIndex: 20,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
          padding: "12px 20px",
          background: "var(--canvas)",
          borderBottom: "1px solid var(--border)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <Monogram />
          <span style={{ fontWeight: 600, letterSpacing: "-0.01em" }}>Agent Kanban</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          {/* Language toggle — RU | EN */}
          <div
            role="group"
            aria-label="Language"
            style={{
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
                className="btn btn-sm"
                style={{
                  borderRadius: 0,
                  border: "none",
                  background:
                    locale === l.code ? "var(--accent)" : "transparent",
                  color: locale === l.code ? "var(--accent-fg)" : "var(--text-dim)",
                  fontWeight: locale === l.code ? 600 : 500,
                  padding: "4px 9px",
                  minWidth: 36,
                }}
                title={l.code === "ru" ? "Русский" : "English"}
              >
                {l.label}
              </button>
            ))}
          </div>
          <button
            className="btn btn-ghost btn-sm"
            onClick={onToggleTheme}
            title={theme === "dark" ? t("nav.theme.toLight") : t("nav.theme.toDark")}
            aria-label={t("nav.theme.toggle")}
          >
            {theme === "dark" ? "☀" : "☾"}
          </button>
          {me?.is_admin && onAdmin && (
            <button className="btn btn-ghost btn-sm" onClick={onAdmin}>
              {t("nav.admin")}
            </button>
          )}
          <button className="btn btn-ghost btn-sm" onClick={logout}>
            {t("nav.logout")}
          </button>
        </div>
      </header>
      <div style={{ flex: 1, minHeight: 0 }}>{children}</div>
    </div>
  );
}

/** Amber monogram — three kanban columns, the board's own mark (not "СД"). */
function Monogram() {
  return (
    <span
      aria-hidden
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        width: 28,
        height: 28,
        borderRadius: 7,
        background: "var(--accent)",
        color: "var(--accent-fg)",
        boxShadow: "0 0 0 1px var(--accent-pressed) inset",
      }}
    >
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
        <rect x="1" y="2" width="3" height="10" rx="1" fill="currentColor" />
        <rect x="5.5" y="2" width="3" height="7" rx="1" fill="currentColor" opacity="0.6" />
        <rect x="10" y="2" width="3" height="9" rx="1" fill="currentColor" opacity="0.4" />
      </svg>
    </span>
  );
}
