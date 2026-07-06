import { useEffect, useState } from "react";
import { api } from "./api";
import { Login } from "./pages/Login";
import { Admin } from "./pages/Admin";
import { Board } from "./pages/Board";
import { CardDetail } from "./pages/CardDetail";

type View = { name: "loading" } | { name: "login" } | { name: "board" } | { name: "admin" } | { name: "card"; taskId: number };

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
    recheck();
    const onUnauthorized = () => { setMe(null); setView({ name: "login" }); };
    window.addEventListener("kanban:unauthorized", onUnauthorized);
    return () => window.removeEventListener("kanban:unauthorized", onUnauthorized);
  }, []);

  if (view.name === "loading") return <div style={{ padding: 40 }}>Loading…</div>;
  if (view.name === "login") return <Login onLoggedIn={recheck} />;
  if (view.name === "admin") return <Admin onBack={() => setView({ name: "board" })} />;
  if (view.name === "card") return <CardDetail taskId={view.taskId} onBack={() => setView({ name: "board" })} />;

  // Board — add header buttons for admin/logout.
  return (
    <div>
      <div style={{ position: "absolute", top: 16, right: 16, display: "flex", gap: 8 }}>
        {me?.is_admin && <button onClick={() => setView({ name: "admin" })}>Admin</button>}
        <button onClick={async () => { await api.logout(); recheck(); }}>Log out</button>
      </div>
      <Board onOpenTask={(id) => setView({ name: "card", taskId: id })} />
    </div>
  );
}
