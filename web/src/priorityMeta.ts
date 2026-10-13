import type { TaskPriority } from "./types";

/**
 * Per-priority metadata: a translation key for the display label + semantic
 * badge class, mirroring statusMeta.ts. Priority colors are semantic:
 * critical = error red, high = warning amber, medium = neutral, low = dim
 * neutral. The label is resolved via t(labelKey) in the consuming components.
 */
export const PRIORITY_META: Record<
  TaskPriority,
  { labelKey: string; badge: "neutral" | "info" | "warning" | "error" | "success" }
> = {
  critical: { labelKey: "priority.critical", badge: "error" },
  high: { labelKey: "priority.high", badge: "warning" },
  medium: { labelKey: "priority.medium", badge: "neutral" },
  low: { labelKey: "priority.low", badge: "neutral" },
};

export const PRIORITY_ORDER: TaskPriority[] = ["critical", "high", "medium", "low"];
