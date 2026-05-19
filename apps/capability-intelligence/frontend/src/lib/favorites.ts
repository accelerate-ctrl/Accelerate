// IMP-2 — subcap favorites store.
//
// Pillar leads return to the same 20-30 subcaps repeatedly during
// active review periods. Bookmarking eliminates repeated navigation
// to the same deep-dive pages. The store is local-first (mirrored to
// localStorage so it survives reloads); a future Phase-5 follow-up
// can sync to ``users/{uid}.favorites`` in Firestore.

import { useEffect, useSyncExternalStore } from 'react';

const STORAGE_KEY = 'zen-subcap-favorites';

function readInitial(): string[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((s) => typeof s === 'string');
  } catch {
    return [];
  }
}

let current: string[] = readInitial();
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((fn) => fn());
}

function write(next: string[]) {
  current = next;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  } catch {
    /* storage full / disabled — keep the in-memory copy */
  }
  emit();
}

export function getFavorites(): string[] {
  return current;
}

export function isFavorite(subCapId: string): boolean {
  return current.includes(subCapId);
}

export function addFavorite(subCapId: string) {
  if (!subCapId || current.includes(subCapId)) return;
  write([...current, subCapId]);
}

export function removeFavorite(subCapId: string) {
  if (!current.includes(subCapId)) return;
  write(current.filter((s) => s !== subCapId));
}

export function toggleFavorite(subCapId: string) {
  if (isFavorite(subCapId)) removeFavorite(subCapId);
  else addFavorite(subCapId);
}

export function clearFavorites() {
  write([]);
}

function subscribe(fn: () => void) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

/**
 * React hook — re-renders subscribers when favorites change. Uses
 * useSyncExternalStore for React 18 concurrent-rendering safety.
 */
export function useFavorites(): string[] {
  return useSyncExternalStore(
    subscribe,
    () => current,
    () => current,
  );
}

/**
 * Mirrors localStorage changes from other tabs so opening a subcap
 * in tab A immediately reflects in tab B's sidebar.
 */
export function useFavoritesSync() {
  useEffect(() => {
    if (typeof window === 'undefined') return;
    function onStorage(e: StorageEvent) {
      if (e.key !== STORAGE_KEY) return;
      try {
        const parsed = e.newValue ? JSON.parse(e.newValue) : [];
        if (Array.isArray(parsed)) {
          current = parsed.filter((s) => typeof s === 'string');
          emit();
        }
      } catch {
        /* ignore */
      }
    }
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);
}
