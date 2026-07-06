import { useEffect, useState } from "react";
import { api } from "../api";

export function Login({ onLoggedIn }: { onLoggedIn: () => void }) {
  const [mode, setMode] = useState<"login" | "setup">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.setupStatus().then((s) => setMode(s.needs_setup ? "setup" : "login")).catch(() => setMode("login"));
  }, []);

  async function submit() {
    setError(null);
    try {
      if (mode === "setup") {
        // The bootstrap admin is auto-created on first startup. On setup, we
        // just log in with the provided creds (the operator set the bootstrap
        // password via env, OR the auto-generated one was printed to stdout).
        // For a true "set your own password on first run" flow, a /api/setup
        // endpoint would be needed — that's a follow-up. For now, setup mode
        // just instructs the user to check the server logs.
        setError("First-run: the admin password was printed to the server console on first startup. Use it to log in, then change it in Admin.");
        setMode("login");
        return;
      }
      await api.login(username, password);
      onLoggedIn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "login failed");
    }
  }

  return (
    <div style={{ maxWidth: 360, margin: "80px auto", padding: 24, border: "1px solid #ddd", borderRadius: 8 }}>
      <h2 style={{ marginTop: 0 }}>Agent Kanban</h2>
      <input placeholder="username" value={username} onChange={(e) => setUsername(e.target.value)} style={{ width: "100%", marginBottom: 8, boxSizing: "border-box" }} />
      <input type="password" placeholder="password" value={password} onChange={(e) => setPassword(e.target.value)} onKeyDown={(e) => e.key === "Enter" && submit()} style={{ width: "100%", marginBottom: 8, boxSizing: "border-box" }} />
      <button onClick={submit} style={{ width: "100%" }}>Log in</button>
      {error && <div style={{ color: "#dc2626", fontSize: 12, marginTop: 8 }}>{error}</div>}
    </div>
  );
}
