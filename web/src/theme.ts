/**
 * Theme toggle — dark is primary (brandbook §03), light for reading.
 * Persists choice in localStorage; applies via [data-theme] on <html>.
 * No React context: CSS variables cascade from data-theme, so a click
 * just flips the attribute and components re-paint via CSS.
 */

export type Theme = "dark" | "light";

const STORAGE_KEY = "kanban-theme";

export function getStoredTheme(): Theme | null {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    return v === "dark" || v === "light" ? v : null;
  } catch {
    return null;
  }
}

export function getTheme(): Theme {
  // localStorage wins; fall back to the attribute set in index.html (dark).
  return getStoredTheme() ?? (document.documentElement.dataset.theme as Theme) ?? "dark";
}

export function setTheme(t: Theme): void {
  document.documentElement.dataset.theme = t;
  try {
    localStorage.setItem(STORAGE_KEY, t);
  } catch {
    /* ignore — private mode / disabled storage */
  }
}

export function toggleTheme(): Theme {
  const next: Theme = getTheme() === "dark" ? "light" : "dark";
  setTheme(next);
  return next;
}
