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
  async listComments(taskId: number): Promise<Comment[]> {
    return j(await fetch(`${BASE}/tasks/${taskId}/comments`));
  },
  async postComment(taskId: number, content: string, author = "user"): Promise<Comment> {
    return j(
      await fetch(`${BASE}/tasks/${taskId}/comments`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ author, content }),
      })
    );
  },
};

export function subscribeWebSocket(
  taskId: number | null,
  onMessage: (evt: { type: string; [k: string]: unknown }) => void
): WebSocket {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const q = taskId ? `?task_id=${taskId}` : "";
  const ws = new WebSocket(`${proto}//${location.host}/ws${q}`);
  ws.onmessage = (e) => onMessage(JSON.parse(e.data));
  return ws;
}
