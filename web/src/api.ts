import type { Comment, ProgressEvent, Task, TaskStatus } from "./types";

const BASE = "/api";

async function j<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export const api = {
  async listTasks(status?: TaskStatus): Promise<Task[]> {
    const q = status ? `?status=${status}` : "";
    return j(await fetch(`${BASE}/tasks${q}`));
  },
  async getTask(id: number): Promise<Task> {
    return j(await fetch(`${BASE}/tasks/${id}`));
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
        body: JSON.stringify(patch),
      })
    );
  },
  async listProgress(taskId: number): Promise<ProgressEvent[]> {
    return j(await fetch(`${BASE}/tasks/${taskId}/progress`));
  },
  async listLastProgressTimestamps(): Promise<Record<number, string>> {
    return j(await fetch(`${BASE}/progress/last`));
  },
  async listComments(taskId: number): Promise<Comment[]> {
    return j(await fetch(`${BASE}/tasks/${taskId}/comments`));
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
        body: JSON.stringify({ author, content }),
      })
    );
  },
};

export interface WSOptions {
  maxRetries?: number;
  baseDelayMs?: number;
}

export interface WSSubscription {
  close: () => void;
}

export function subscribeWebSocket(
  taskId: number | null,
  onMessage: (evt: { type: string; [k: string]: unknown }) => void,
  options: WSOptions = {}
): WSSubscription {
  const maxRetries = options.maxRetries ?? 5;
  const baseDelayMs = options.baseDelayMs ?? 500;
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const q = taskId ? `?task_id=${taskId}` : "";
  const url = `${proto}//${location.host}/ws${q}`;

  let retryCount = 0;
  let closedByCaller = false;
  let ws: WebSocket | null = null;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  function open() {
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

  open();

  return {
    close: () => {
      closedByCaller = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (ws) ws.close();
    },
  };
}
