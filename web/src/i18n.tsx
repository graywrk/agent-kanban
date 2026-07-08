/**
 * React binding for the i18n store.
 *
 * `useT()` returns a tuple `[t, locale, setLocale, tCount]`. The hook
 * subscribes to the store so any component using it re-renders when the
 * locale flips. `t`/`tCount` are bound to the current locale on each render,
 * so callers don't need to pass it.
 *
 * No Provider is strictly required — the store is module-level — but we expose
 * an `I18nProvider` that sets `document.documentElement.lang` on mount so the
 * initial SSR/HTML attribute is corrected after hydration.
 */
import { useEffect, useState, type ReactNode } from "react";
import {
  getLocale,
  getInitialLocale,
  setLocale as storeSetLocale,
  subscribe,
  t as _t,
  tCount as _tCount,
  localeBcp47 as _localeBcp47,
  LANGS as _LANGS,
  type Locale,
} from "./i18n";

// Re-export the engine symbols so consumers can import everything from one path.
export const LANGS = _LANGS;
export const localeBcp47 = _localeBcp47;
export type { Locale };

export function useT() {
  // Subscribe so we re-render when the locale changes.
  const [locale, setLocal] = useState<Locale>(getLocale());
  useEffect(() => subscribe(setLocal), []);

  const setLocale = (next: Locale) => storeSetLocale(next);
  // Bind translators to the current locale on each render.
  const t = (key: string, params?: Record<string, string | number>) => _t(key, params);
  const tCount = (key: string, count: number) => _tCount(key, count);
  return { t, tCount, locale, setLocale };
}

export function I18nProvider({ children }: { children: ReactNode }) {
  // Correct the <html lang> attribute on mount (index.html defaults to "en").
  useEffect(() => {
    document.documentElement.lang = getInitialLocale();
  }, []);
  return <>{children}</>;
}
