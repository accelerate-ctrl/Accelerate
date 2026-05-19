// IMP-14 — Mission Control catalogue changelog tile.

import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import MissionControl from '../src/pages/MissionControl';

function setupFetch(opts: { ageDays: number; runId?: string }) {
  const started = new Date(Date.now() - opts.ageDays * 86400000).toISOString();
  globalThis.fetch = vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input.toString();
    if (url.includes('/catalogue/overview')) {
      return new Response(
        JSON.stringify({
          pillars: {},
          totals: { pillars_loaded: 1, subcaps: 205, open_flags: 0 },
          last_ingest: {
            run_id: opts.runId ?? 'ingest-12345',
            started_at: started,
            completed_at: started,
            pillars_loaded: ['P1', 'P2'],
          },
        }),
        { status: 200 },
      );
    }
    if (url.includes('/catalogue/structure')) {
      return new Response(
        JSON.stringify({
          totals: { pillars: 4, categories: 30, l1s: 60, subcaps: 205 },
          pillars: [],
        }),
        { status: 200 },
      );
    }
    return new Response('', { status: 404 });
  }) as unknown as typeof fetch;
}

function renderControl() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <MissionControl />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

describe('Mission Control changelog tile (IMP-14)', () => {
  test('renders the tile for a recent ingest', async () => {
    setupFetch({ ageDays: 2 });
    renderControl();
    expect(await screen.findByText(/catalogue updated/i)).toBeInTheDocument();
    expect(screen.getByText(/View version timeline/i)).toBeInTheDocument();
    expect(screen.getByText(/Open diff viewer/i)).toBeInTheDocument();
  });

  test('does not render for ingests older than 7 days', async () => {
    setupFetch({ ageDays: 10 });
    renderControl();
    // Wait for the page to settle, then assert the tile is absent.
    await screen.findByText(/Mission Control/i);
    await waitFor(() => {
      // Other content from the page should have rendered; the tile
      // specifically should not.
      expect(screen.queryByText(/Catalogue updated/i)).not.toBeInTheDocument();
    });
  });

  test('dismiss persists per-run via localStorage', async () => {
    setupFetch({ ageDays: 1, runId: 'ingest-abc' });
    renderControl();
    await screen.findByText(/catalogue updated/i);
    const dismissBtn = screen.getByRole('button', { name: /dismiss catalogue update/i });
    fireEvent.click(dismissBtn);
    await waitFor(() => {
      expect(screen.queryByText(/catalogue updated/i)).not.toBeInTheDocument();
    });
    expect(window.localStorage.getItem('mc-changelog-dismissed:ingest-abc')).toBe('1');
  });

  test('does not render when dismissal flag exists for the run', async () => {
    window.localStorage.setItem('mc-changelog-dismissed:ingest-xyz', '1');
    setupFetch({ ageDays: 1, runId: 'ingest-xyz' });
    renderControl();
    await screen.findByText(/Mission Control/i);
    await waitFor(() => {
      expect(screen.queryByText(/catalogue updated/i)).not.toBeInTheDocument();
    });
  });

  test('new run_id resurfaces the tile even after a prior dismissal', async () => {
    window.localStorage.setItem('mc-changelog-dismissed:ingest-old', '1');
    setupFetch({ ageDays: 1, runId: 'ingest-new' });
    renderControl();
    expect(await screen.findByText(/catalogue updated/i)).toBeInTheDocument();
  });
});
