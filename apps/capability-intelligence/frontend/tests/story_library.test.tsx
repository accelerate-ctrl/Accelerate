// Story Library paginated listing (IMP-3 / Phase 2.2).

import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';
import {
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import StoryLibrary from '../src/pages/StoryLibrary';

const canonicalRows = Array.from({ length: 150 }, (_, i) => ({
  story_key: `P1C1.1.1.S${i}`,
  sub_cap_id: 'P1C1.1.1',
  summary: `Story ${i} about ${i % 3 === 0 ? 'open banking' : 'governance'}`,
  confidence_level: 'HIGH',
}));

function setupFetch() {
  globalThis.fetch = vi
    .fn()
    .mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString();
      const method = init?.method || 'GET';
      if (method === 'GET' && url.includes('/stories/canonical/paged')) {
        const u = new URL(url, 'http://localhost');
        const offset = Number(u.searchParams.get('offset') ?? 0);
        const limit = Number(u.searchParams.get('limit') ?? 100);
        const q = u.searchParams.get('q');
        let rows = canonicalRows;
        if (q) rows = rows.filter((r) => r.summary.includes(q));
        return new Response(
          JSON.stringify({
            total: rows.length,
            offset,
            limit,
            rows: rows.slice(offset, offset + limit),
          }),
          { status: 200 },
        );
      }
      if (method === 'GET' && url.includes('/stories/jira/paged')) {
        return new Response(
          JSON.stringify({ total: 0, offset: 0, limit: 100, rows: [] }),
          { status: 200 },
        );
      }
      return new Response('', { status: 404 });
    }) as unknown as typeof fetch;
}

function renderLib() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <StoryLibrary />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  setupFetch();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('Story Library (paginated)', () => {
  test('renders the first page plus a load-more affordance', async () => {
    renderLib();
    await screen.findByText('P1C1.1.1.S0');
    expect(screen.getByText(/100 \/ 150/)).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /load more.*50 remaining/i }),
    ).toBeInTheDocument();
  });

  test('load more grows the visible page', async () => {
    renderLib();
    await screen.findByText('P1C1.1.1.S0');
    fireEvent.click(
      screen.getByRole('button', { name: /load more.*50 remaining/i }),
    );
    // After load more we expect 150/150 and the last row to appear.
    await waitFor(() => {
      expect(screen.getByText('P1C1.1.1.S149')).toBeInTheDocument();
    });
    expect(screen.getByText(/150 \/ 150/)).toBeInTheDocument();
  });

  test('filter narrows the corpus via server-side search', async () => {
    renderLib();
    await screen.findByText('P1C1.1.1.S0');
    const input = screen.getByPlaceholderText(/filter the full corpus/i);
    fireEvent.change(input, { target: { value: 'open banking' } });
    // After debounce, the count drops to ~50 (1/3 of 150).
    await waitFor(() => {
      expect(screen.getByText(/\/ 50/)).toBeInTheDocument();
    }, { timeout: 1500 });
  });

  test('shows Jira empty-state when no rows', async () => {
    renderLib();
    expect(
      await screen.findByText(/Atlassian creds not configured/i),
    ).toBeInTheDocument();
  });
});
