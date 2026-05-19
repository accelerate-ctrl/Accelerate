// Theme store / toggle behaviour (UI/UX Brief §8.1 / §8.2).

import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

describe('theme store', () => {
  beforeEach(() => {
    document.documentElement.setAttribute('data-theme', 'light');
    window.localStorage.clear();
    // Force a fresh module so `currentTheme` resets per test.
    vi.resetModules();
  });

  afterEach(() => {
    document.documentElement.removeAttribute('data-theme');
    window.localStorage.clear();
  });

  test('reads initial theme from the data-theme attribute', async () => {
    document.documentElement.setAttribute('data-theme', 'dark');
    const { getTheme } = await import('@/lib/theme');
    expect(getTheme()).toBe('dark');
  });

  test('setTheme updates document attribute and localStorage', async () => {
    const { setTheme, getTheme } = await import('@/lib/theme');
    setTheme('dark');
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
    expect(window.localStorage.getItem('zen-theme')).toBe('dark');
    expect(getTheme()).toBe('dark');
  });

  test('toggleTheme flips between light and dark', async () => {
    const { toggleTheme, getTheme } = await import('@/lib/theme');
    const before = getTheme();
    toggleTheme();
    expect(getTheme()).not.toBe(before);
    toggleTheme();
    expect(getTheme()).toBe(before);
  });

  test('setTheme is idempotent', async () => {
    const { setTheme, getTheme } = await import('@/lib/theme');
    setTheme('light');
    setTheme('light');
    expect(getTheme()).toBe('light');
  });
});

describe('ThemeToggle', () => {
  beforeEach(() => {
    document.documentElement.setAttribute('data-theme', 'light');
    window.localStorage.clear();
    vi.resetModules();
  });

  test('renders an accessible toggle that flips data-theme on click', async () => {
    const { default: ThemeToggle } = await import('@/components/ThemeToggle');
    render(<ThemeToggle />);
    const btn = screen.getByRole('button', { name: /switch to dark mode/i });
    fireEvent.click(btn);
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
    // After flip, the aria-label inverts.
    expect(
      screen.getByRole('button', { name: /switch to light mode/i }),
    ).toBeInTheDocument();
  });
});
