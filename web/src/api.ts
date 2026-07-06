import type { Comment, ProgressEvent, Task, TaskStatus } from "./types";

const BASE = "/api";

async function j<T>(res: Response): Promise<T> {
  if (res.status === 401) {
    window.dispatchEvent(new CustomEvent("kanban:unauthorized"));
    throw new Error("unauthorized");
  }
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export const api = {
  async listTasks(status?: TaskStatus): Promise<Task[]> {
    const q = status ? `?status=${status}` : "";
    return j(await fetch(`${BASE}/tasks${q}`, { credentials: "include" }));
  },
  async getTask(id: number): Promise<Task> {
    return j(await fetch(`${BASE}/tasks/${id}`, { credentials: "include" }));
  },
  async createTask(data: {
    title: string;
    description?: string;
    tags?: string[];
    status?: TaskStatus;
    repo_path?: string;
    base_branch?: string;
  }): Promise<Task> {
    return j(
      await fetch(`${BASE}/tasks`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(data),
      })
    );
  },
  async updateTask(
    id: number,
    patch: Partial<Pick<Task, "title" | "description" | "tags" | "status" | "sort_order">>
  ): Promise<Task> {
    return j(
      await fetch(`${BASE}/tasks/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(patch),
      })
    );
  },
  async listProgress(taskId: number): Promise<ProgressEvent[]> {
    return j(await fetch(`${BASE}/tasks/${taskId}/progress`, { credentials: "include" }));
  },
  async listLastProgressTimestamps(): Promise<Record<number, string>> {
    return j(await fetch(`${BASE}/progress/last`, { credentials: "include" }));
  },
  async listComments(taskId: number): Promise<Comment[]> {
    return j(await fetch(`${BASE}/tasks/${taskId}/comments`, { credentials: "include" }));
  },
  async postComment(
    taskId: number,
    content: string,
    author = "user",
    status?: "in_progress" | "ready"
  ): Promise<Comment> {
    const q = status ? `?status=${status}` : "";
    return j(
      await fetch(`${BASE}/tasks/${taskId}/comments${q}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ author, content }),
      })
    );
  },

  // ---- Auth ----
  async login(username: string, password: string): Promise<{ username: string; is_admin: boolean }> {
    return j(await fetch(`${BASE}/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ username, password }),
    }));
  },
  async logout(): Promise<void> {
    await fetch(`${BASE}/logout`, { method: "POST", credentials: "include" });
  },
  async me(): Promise<{ kind: string; agent_name: string; is_admin: boolean }> {
    return j(await fetch(`${BASE}/me`, { credentials: "include" }));
  },
  async setupStatus(): Promise<{ needs_setup: boolean }> {
    return j(await fetch(`${BASE}/setup-status`, { credentials: "include" }));
  },
  async listTokens(): Promise<Array<{ id: number; agent_name: string; description: string | null; created_at: string; last_used_at: string | null }>> {
    return j(await fetch(`${BASE}/tokens`, { credentials: "include" }));
  },
  async createToken(agent_name: string, description?: string): Promise<{ id: number; agent_name: string; description: string | null; token: string }> {
    return j(await fetch(`${BASE}/tokens`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ agent_name, description }),
    }));
  },
  async deleteToken(id: number): Promise<void> {
    await fetch(`${BASE}/tokens/${id}`, { method: "DELETE", credentials: "include" });
  },
  async listUsers(): Promise<Array<{ id: number; username: string; is_admin: boolean; created_at: string }>> {
    return j(await fetch(`${BASE}/users`, { credentials: "include" }));
  },
  async createUser(username: string, password: string, is_admin: boolean): Promise<void> {
    await fetch(`${BASE}/users`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ username, password, is_admin }),
    });
  },
  async deleteUser(id: number): Promise<void> {
    await fetch(`${BASE}/users/${id}`, { method: "DELETE", credentials: "include" });
  },
  async fetchWsTicket(): Promise<{ ticket: string; expires_in: number }> {
    return j(await fetch(`${BASE}/ws-ticket`, { method: "POST", credentials: "include" }));
  },
  async setup(username: string, password: string): Promise<void> {
    await fetch(`${BASE}/setup`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ username, password }),
    });
  },
  async updateUser(
    id: number,
    patch: { current_password?: string; password?: string; is_admin?: boolean }
  ): Promise<{ id: number; username: string; is_admin: boolean }> {
    return j(await fetch(`${BASE}/users/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify(patch),
    }));
  },
};

export interface WSOptions {
  maxRetries?: number;
  baseDelayMs?: number;
}

export interface WSSubscription {
  close: () => void;
}

export async function subscribeWebSocket(
  taskId: number | null,
  onMessage: (evt: { type: string; [k: string]: unknown }) => void,
  options: WSOptions = {}
): Promise<WSSubscription> {
  const maxRetries = options.maxRetries ?? 5;
  const baseDelayMs = options.baseDelayMs ?? 500;
  const proto = location.protocol === "https:" ? "wss:" : "ws:";

  let retryCount = 0;
  let closedByCaller = false;
  let ws: WebSocket | null = null;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  async function open() {
    // Fetch a fresh single-use ticket each time we (re)connect. The ticket
    // keeps the long-lived bearer out of proxy/access logs (the WS URL is
    // logged); the session cookie remains the primary auth for same-origin.
    const qParts: string[] = [];
    if (taskId) qParts.push(`task_id=${taskId}`);
    try {
      const { ticket } = await api.fetchWsTicket();
      qParts.push(`ticket=${encodeURIComponent(ticket)}`);
    } catch {
      // Cookie-only fallback (same-origin). Continue without ticket.
    }
    const q = qParts.length ? `?${qParts.join("&")}` : "";
    const url = `${proto}//${location.host}/ws${q}`;
    ws = new WebSocket(url);
    ws.onopen = () => {
      retryCount = 0;
    };
    ws.onmessage = (e) => {
      try {
        onMessage(JSON.parse(e.data));
      } catch (err) {
        console.error("kanban: bad WS message", err);
      }
    };
    ws.onerror = (err) => {
      console.error("kanban: WS error", err);
    };
    ws.onclose = () => {
      if (closedByCaller) return;
      if (retryCount >= maxRetries) {
        console.error(`kanban: WS giving up after ${maxRetries} retries`);
        return;
      }
      const delay = baseDelayMs * Math.pow(2, retryCount);
      retryCount += 1;
      reconnectTimer = setTimeout(open, delay);
    };
  }

  await open();

  return {
    close: () => {
      closedByCaller = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (ws) ws.close();
    },
  };
}
