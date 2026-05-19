// Theme store + sync to <html data-theme="…"> and localStorage.
// Mirrors UI/UX Brief §8.1/§8.2: an inline FOUC-prevention script in
// index.html sets data-theme before React paints; this store keeps it in
// sync with user interaction and (later) Firestore preferences.

import { useEffect, useSyncExternalStore } from 'react';

export type Theme = 'light' | 'dark';

const STORAGE_KEY = 'zen-theme';

function readInitial(): Theme {
  if (typeof document === 'undefined') return 'light';
  const attr = document.documentElement.getAttribute('data-theme');
  if (attr === 'dark' || attr === 'light') return attr;
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === 'dark' || stored === 'light') return stored;
  } catch {
    /* ignore */
  }
  if (typeof window !== 'undefined' && window.matchMedia) {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  return 'light';
}

let currentTheme: Theme = readInitial();
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((fn) => fn());
}

export function getTheme(): Theme {
  return currentTheme;
}

export function setTheme(next: Theme) {
  if (next === currentTheme) return;
  currentTheme = next;
  if (typeof document !== 'undefined') {
    document.documentElement.setAttribute('data-theme', next);
  }
  try {
    window.localStorage.setItem(STORAGE_KEY, next);
  } catch {
    /* ignore */
  }
  emit();
}

export function toggleTheme() {
  setTheme(currentTheme === 'dark' ? 'light' : 'dark');
}

function subscribe(fn: () => void) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

// React hook — returns the current theme and re-renders on change. Uses
// useSyncExternalStore so it's safe under React 18 concurrent rendering.
export function useTheme(): Theme {
  return useSyncExternalStore(
    subscribe,
    () => currentTheme,
    () => currentTheme,
  );
}

// Optional effect that mirrors OS preference changes when the user has
// not explicitly chosen a theme. Mount once in the App root.
export function useSystemThemeSync() {
  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return;
    let hasUserChoice = false;
    try {
      hasUserChoice = !!window.localStorage.getItem(STORAGE_KEY);
    } catch {
      /* ignore */
    }
    if (hasUserChoice) return;
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const handler = (e: MediaQueryListEvent) => setTheme(e.matches ? 'dark' : 'light');
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);
}
