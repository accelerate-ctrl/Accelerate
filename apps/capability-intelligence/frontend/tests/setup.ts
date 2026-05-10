import '@testing-library/jest-dom/vitest';

// jsdom doesn't ship matchMedia (recharts uses it).
if (typeof window !== 'undefined' && !window.matchMedia) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: () => ({
      matches: false,
      media: '',
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  });
}

// Provide a default fetch mock that returns 404; individual tests override it.
if (typeof globalThis.fetch === 'undefined') {
  (globalThis as unknown as { fetch: typeof fetch }).fetch = (async () =>
    new Response('', { status: 404 })) as unknown as typeof fetch;
}
