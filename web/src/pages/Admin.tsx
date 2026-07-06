import { useEffect, useState } from "react";
import { api } from "../api";

interface TokenRow { id: number; agent_name: string; description: string | null; created_at: string; last_used_at: string | null }
interface UserRow { id: number; username: string; is_admin: boolean; created_at: string }

export function Admin({ onBack }: { onBack: () => void }) {
  const [tokens, setTokens] = useState<TokenRow[]>([]);
  const [users, setUsers] = useState<UserRow[]>([]);
  const [newTokenAgent, setNewTokenAgent] = useState("");
  const [newTokenDesc, setNewTokenDesc] = useState("");
  const [mintedToken, setMintedToken] = useState<string | null>(null);
  const [newUser, setNewUser] = useState({ username: "", password: "", is_admin: false });

  async function refresh() {
    setTokens(await api.listTokens());
    setUsers(await api.listUsers());
  }
  useEffect(() => { refresh(); }, []);

  async function mint() {
    if (!newTokenAgent.trim()) return;
    const t = await api.createToken(newTokenAgent, newTokenDesc || undefined);
    setMintedToken(t.token);
    setNewTokenAgent(""); setNewTokenDesc("");
    refresh();
  }
  async function revoke(id: number) {
    await api.deleteToken(id);
    refresh();
  }
  async function addUser() {
    if (!newUser.username || !newUser.password) return;
    await api.createUser(newUser.username, newUser.password, newUser.is_admin);
    setNewUser({ username: "", password: "", is_admin: false });
    refresh();
  }
  async function removeUser(id: number) {
    await api.deleteUser(id);
    refresh();
  }

  return (
    <div style={{ padding: 16, maxWidth: 900, margin: "0 auto" }}>
      <button onClick={onBack}>← Back to board</button>
      <h2>Admin</h2>

      <h3>Tokens (agents)</h3>
      {mintedToken && (
        <div style={{ background: "#ecfdf5", border: "1px solid #6ee7b7", padding: 12, borderRadius: 6, marginBottom: 12, fontFamily: "monospace", fontSize: 12, wordBreak: "break-all" }}>
          Copy this token now — it won't be shown again:<br />
          {mintedToken}
          <button onClick={() => setMintedToken(null)} style={{ marginLeft: 8 }}>dismiss</button>
        </div>
      )}
      <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
        <input placeholder="agent_name (e.g. codex)" value={newTokenAgent} onChange={(e) => setNewTokenAgent(e.target.value)} />
        <input placeholder="description (optional)" value={newTokenDesc} onChange={(e) => setNewTokenDesc(e.target.value)} />
        <button onClick={mint}>Mint</button>
      </div>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
        <thead><tr><th align="left">agent</th><th align="left">description</th><th align="left">created</th><th align="left">last used</th><th></th></tr></thead>
        <tbody>
          {tokens.map((t) => (
            <tr key={t.id}>
              <td>{t.agent_name}</td><td>{t.description}</td>
              <td>{new Date(t.created_at).toLocaleString()}</td>
              <td>{t.last_used_at ? new Date(t.last_used_at).toLocaleString() : "never"}</td>
              <td><button onClick={() => revoke(t.id)}>revoke</button></td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3 style={{ marginTop: 24 }}>Users</h3>
      <div style={{ display: "flex", gap: 8, marginBottom: 8, alignItems: "center" }}>
        <input placeholder="username" value={newUser.username} onChange={(e) => setNewUser({ ...newUser, username: e.target.value })} />
        <input type="password" placeholder="password" value={newUser.password} onChange={(e) => setNewUser({ ...newUser, password: e.target.value })} />
        <label><input type="checkbox" checked={newUser.is_admin} onChange={(e) => setNewUser({ ...newUser, is_admin: e.target.checked })} /> admin</label>
        <button onClick={addUser}>Add</button>
      </div>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
        <thead><tr><th align="left">username</th><th align="left">admin</th><th align="left">created</th><th></th></tr></thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.id}>
              <td>{u.username}</td><td>{u.is_admin ? "✓" : ""}</td>
              <td>{new Date(u.created_at).toLocaleString()}</td>
              <td><button onClick={() => removeUser(u.id)}>delete</button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
