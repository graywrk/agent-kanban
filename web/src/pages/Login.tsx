import { useEffect, useState } from "react";
import { api } from "../api";

export function Login({ onLoggedIn }: { onLoggedIn: () => void }) {
  const [mode, setMode] = useState<"login" | "setup">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.setupStatus().then((s) => setMode(s.needs_setup ? "setup" : "login")).catch(() => setMode("login"));
  }, []);

  async function submit() {
    setError(null);
    try {
      if (mode === "setup") {
        // Create the first admin via /api/setup, then log in with the new
        // creds. The server only allows setup when no users exist yet.
        if (password.length < 8) {
          setError("password must be at least 8 characters");
          return;
        }
        if (password !== confirm) {
          setError("passwords do not match");
          return;
        }
        await api.setup(username || "admin", password);
        await api.login(username || "admin", password);
        onLoggedIn();
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
      {mode === "setup" && (
        <div style={{ fontSize: 12, color: "#666", marginBottom: 8 }}>
          First run: create the admin account.
        </div>
      )}
      <input placeholder="username" value={username} onChange={(e) => setUsername(e.target.value)} style={{ width: "100%", marginBottom: 8, boxSizing: "border-box" }} />
      <input type="password" placeholder="password" value={password} onChange={(e) => setPassword(e.target.value)} onKeyDown={(e) => e.key === "Enter" && submit()} style={{ width: "100%", marginBottom: 8, boxSizing: "border-box" }} />
      {mode === "setup" && (
        <input
          type="password"
          placeholder="confirm password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          style={{ width: "100%", marginBottom: 8, boxSizing: "border-box" }}
        />
      )}
      <button onClick={submit} style={{ width: "100%" }}>{mode === "setup" ? "Set up" : "Log in"}</button>
      {error && <div style={{ color: "#dc2626", fontSize: 12, marginTop: 8 }}>{error}</div>}
    </div>
  );
}
