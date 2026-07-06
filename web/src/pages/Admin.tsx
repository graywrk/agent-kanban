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
  const [actionError, setActionError] = useState<string | null>(null);
  const [editingUserId, setEditingUserId] = useState<number | null>(null);

  async function refresh() {
    setTokens(await api.listTokens());
    setUsers(await api.listUsers());
  }
  useEffect(() => { refresh(); }, []);

  async function mint() {
    if (!newTokenAgent.trim()) return;
    setActionError(null);
    try {
      const t = await api.createToken(newTokenAgent, newTokenDesc || undefined);
      setMintedToken(t.token);
      setNewTokenAgent(""); setNewTokenDesc("");
      refresh();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Failed to mint token");
    }
  }
  async function revoke(id: number) {
    setActionError(null);
    try {
      await api.deleteToken(id);
      refresh();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Failed to revoke token");
    }
  }
  async function addUser() {
    if (!newUser.username || !newUser.password) return;
    setActionError(null);
    try {
      await api.createUser(newUser.username, newUser.password, newUser.is_admin);
      setNewUser({ username: "", password: "", is_admin: false });
      refresh();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Failed to add user");
    }
  }
  async function removeUser(id: number) {
    setActionError(null);
    try {
      await api.deleteUser(id);
      if (editingUserId === id) setEditingUserId(null);
      refresh();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Failed to remove user");
    }
  }

  return (
    <div style={{ padding: 16, maxWidth: 900, margin: "0 auto" }}>
      <button onClick={onBack}>← Back to board</button>
      <h2>Admin</h2>

      {actionError && (
        <div style={{ color: "#dc2626", fontSize: 12, marginBottom: 12 }}>{actionError}</div>
      )}

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
            <UserRowView
              key={u.id}
              user={u}
              editing={editingUserId === u.id}
              onToggleEdit={() => setEditingUserId(editingUserId === u.id ? null : u.id)}
              onSaved={() => { setEditingUserId(null); refresh(); }}
              onError={(msg) => setActionError(msg)}
              onDelete={() => removeUser(u.id)}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function UserRowView({
  user,
  editing,
  onToggleEdit,
  onSaved,
  onError,
  onDelete,
}: {
  user: UserRow;
  editing: boolean;
  onToggleEdit: () => void;
  onSaved: () => void;
  onError: (msg: string) => void;
  onDelete: () => void;
}) {
  // Password change fields. current_password is the ACTING admin's password
  // (re-proving identity), password is the target user's new password.
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [busy, setBusy] = useState(false);

  async function changePassword() {
    if (!currentPassword || !newPassword) return;
    setBusy(true);
    try {
      await api.updateUser(user.id, { current_password: currentPassword, password: newPassword });
      setCurrentPassword("");
      setNewPassword("");
      onSaved();
    } catch (e) {
      onError(e instanceof Error ? e.message : "Failed to change password");
    } finally {
      setBusy(false);
    }
  }

  async function toggleAdmin(next: boolean) {
    setBusy(true);
    try {
      await api.updateUser(user.id, { is_admin: next });
      onSaved();
    } catch (e) {
      onError(e instanceof Error ? e.message : "Failed to update admin flag");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <tr>
        <td>{user.username}</td>
        <td>
          <label>
            <input
              type="checkbox"
              checked={user.is_admin}
              disabled={busy || user.is_admin === true}
              onChange={(e) => toggleAdmin(e.target.checked)}
              title={user.is_admin ? "uncheck via edit to demote" : "promote to admin"}
            />{" "}
            {user.is_admin ? "✓ admin" : ""}
          </label>
        </td>
        <td>{new Date(user.created_at).toLocaleString()}</td>
        <td>
          <button onClick={onToggleEdit}>{editing ? "close" : "edit"}</button>
        </td>
      </tr>
      {editing && (
        <tr>
          <td colSpan={4} style={{ background: "#fafafa", padding: 8 }}>
            <div style={{ fontSize: 12, color: "#666", marginBottom: 6 }}>
              Change password — enter <strong>your</strong> current admin password and a new password (8+) for {user.username}.
            </div>
            <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
              <input
                type="password"
                placeholder="your current password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                style={{ width: 200 }}
              />
              <input
                type="password"
                placeholder={`new password for ${user.username}`}
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                style={{ width: 200 }}
              />
              <button onClick={changePassword} disabled={busy || !currentPassword || !newPassword}>
                Change password
              </button>
              {!user.is_admin && (
                <button onClick={() => toggleAdmin(true)} disabled={busy}>promote to admin</button>
              )}
              {user.is_admin && (
                <button onClick={() => toggleAdmin(false)} disabled={busy}>demote</button>
              )}
              <button onClick={onDelete} disabled={busy}>delete user</button>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}
