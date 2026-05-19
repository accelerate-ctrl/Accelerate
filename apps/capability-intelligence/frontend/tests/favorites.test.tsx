// IMP-2 — subcap favorites store tests.

import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, test } from 'vitest';
import {
  addFavorite,
  clearFavorites,
  getFavorites,
  isFavorite,
  removeFavorite,
  toggleFavorite,
  useFavorites,
  useFavoritesSync,
} from '@/lib/favorites';

const STORAGE_KEY = 'zen-subcap-favorites';

beforeEach(() => {
  window.localStorage.clear();
  clearFavorites();
});

afterEach(() => {
  window.localStorage.clear();
  clearFavorites();
});

describe('favorites store', () => {
  test('addFavorite persists and dedupes', () => {
    addFavorite('P1C1.1.1');
    addFavorite('P1C1.1.1');
    addFavorite('P2C2.2.2');
    expect(getFavorites()).toEqual(['P1C1.1.1', 'P2C2.2.2']);
    expect(JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? '[]')).toEqual([
      'P1C1.1.1',
      'P2C2.2.2',
    ]);
  });

  test('removeFavorite is a no-op when not present', () => {
    addFavorite('P1C1.1.1');
    removeFavorite('P9C9.9.9');
    expect(getFavorites()).toEqual(['P1C1.1.1']);
  });

  test('removeFavorite drops the entry', () => {
    addFavorite('P1C1.1.1');
    addFavorite('P2C2.2.2');
    removeFavorite('P1C1.1.1');
    expect(getFavorites()).toEqual(['P2C2.2.2']);
  });

  test('toggleFavorite flips state', () => {
    expect(isFavorite('P1C1.1.1')).toBe(false);
    toggleFavorite('P1C1.1.1');
    expect(isFavorite('P1C1.1.1')).toBe(true);
    toggleFavorite('P1C1.1.1');
    expect(isFavorite('P1C1.1.1')).toBe(false);
  });

  test('clearFavorites empties the list', () => {
    addFavorite('P1C1.1.1');
    addFavorite('P2C2.2.2');
    clearFavorites();
    expect(getFavorites()).toEqual([]);
  });

  test('addFavorite ignores empty id', () => {
    addFavorite('');
    expect(getFavorites()).toEqual([]);
  });
});

describe('useFavorites hook', () => {
  test('re-renders on add/remove', () => {
    const { result } = renderHook(() => useFavorites());
    expect(result.current).toEqual([]);
    act(() => addFavorite('P1C1.1.1'));
    expect(result.current).toEqual(['P1C1.1.1']);
    act(() => addFavorite('P2C2.2.2'));
    expect(result.current).toEqual(['P1C1.1.1', 'P2C2.2.2']);
    act(() => removeFavorite('P1C1.1.1'));
    expect(result.current).toEqual(['P2C2.2.2']);
  });
});

describe('useFavoritesSync', () => {
  test('reflects storage events from other tabs', () => {
    renderHook(() => useFavoritesSync());
    const event = new StorageEvent('storage', {
      key: STORAGE_KEY,
      newValue: JSON.stringify(['P3C3.3.3', 'P4C4.4.4']),
    });
    act(() => {
      window.dispatchEvent(event);
    });
    expect(getFavorites()).toEqual(['P3C3.3.3', 'P4C4.4.4']);
  });

  test('ignores storage events for unrelated keys', () => {
    renderHook(() => useFavoritesSync());
    addFavorite('P1C1.1.1');
    const event = new StorageEvent('storage', {
      key: 'unrelated-key',
      newValue: JSON.stringify(['ignored']),
    });
    act(() => {
      window.dispatchEvent(event);
    });
    expect(getFavorites()).toEqual(['P1C1.1.1']);
  });

  test('tolerates malformed JSON from other tab', () => {
    renderHook(() => useFavoritesSync());
    addFavorite('P1C1.1.1');
    const event = new StorageEvent('storage', {
      key: STORAGE_KEY,
      newValue: '{not json',
    });
    act(() => {
      window.dispatchEvent(event);
    });
    // Pre-existing in-memory state is preserved.
    expect(getFavorites()).toEqual(['P1C1.1.1']);
  });

  test('null newValue clears favorites', () => {
    addFavorite('P1C1.1.1');
    renderHook(() => useFavoritesSync());
    const event = new StorageEvent('storage', {
      key: STORAGE_KEY,
      newValue: null,
    });
    act(() => {
      window.dispatchEvent(event);
    });
    expect(getFavorites()).toEqual([]);
  });
});
