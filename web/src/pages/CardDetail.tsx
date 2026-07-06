// Stub: replaced by full implementation in Task 15.
export function CardDetail({ taskId, onBack }: { taskId: number; onBack: () => void }) {
  return (
    <div style={{ padding: 16 }}>
      <button onClick={onBack}>← Back</button>
      <h2>Task #{taskId}</h2>
      <p>Loading detail…</p>
    </div>
  );
}
