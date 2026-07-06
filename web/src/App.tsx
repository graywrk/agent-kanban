import { useState } from "react";
import { Board } from "./pages/Board";
import { CardDetail } from "./pages/CardDetail";

export default function App() {
  const [openTaskId, setOpenTaskId] = useState<number | null>(null);
  return openTaskId === null ? (
    <Board onOpenTask={setOpenTaskId} />
  ) : (
    <CardDetail taskId={openTaskId} onBack={() => setOpenTaskId(null)} />
  );
}
