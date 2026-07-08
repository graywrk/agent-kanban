import type { TaskStatus } from "./types";

/**
 * Per-status metadata: a translation key for the display label + semantic
 * badge class. Status colors are strictly semantic (brandbook §03):
 * success/warning/error/info/neutral. The label is resolved via t(labelKey)
 * in the consuming components (Column, CardDetail).
 */
export const STATUS_META: Record<
  TaskStatus,
  { labelKey: string; badge: "neutral" | "info" | "warning" | "success" | "error" }
> = {
  todo: { labelKey: "status.todo", badge: "neutral" },
  ready: { labelKey: "status.ready", badge: "info" },
  in_progress: { labelKey: "status.in_progress", badge: "warning" },
  review: { labelKey: "status.review", badge: "warning" },
  done: { labelKey: "status.done", badge: "success" },
  blocked: { labelKey: "status.blocked", badge: "error" },
  cancelled: { labelKey: "status.cancelled", badge: "neutral" },
};
