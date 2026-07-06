import { useEffect, useState } from "react";
import { api } from "./api";
import type { Task } from "./types";

export default function App() {
  const [tasks, setTasks] = useState<Task[]>([]);
  useEffect(() => {
    api.listTasks().then(setTasks).catch(console.error);
  }, []);
  return (
    <div style={{ padding: 20 }}>
      <h1>Agent Kanban</h1>
      <ul>
        {tasks.map((t) => (
          <li key={t.id}>
            #{t.id} {t.title} — <em>{t.status}</em>
          </li>
        ))}
      </ul>
    </div>
  );
}
