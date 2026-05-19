// Phase 5 — QaHealthTile smoke tests.

import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import QaHealthTile from '@/components/QaHealthTile';

function setupFetch(overrides: Record<string, unknown> = {}) {
  const defaults: Record<string, unknown> = {
    '/qa/budgets/me': {
      user_email: 'alice@zen',
      spend_usd: 2.5,
      budget_usd: 5.0,
      fraction: 0.5,
      should_downgrade: false,
      admin_override: false,
      headroom_usd: 2.5,
    },
    '/qa/source-health/latest': {
      n_sources_seen: 12,
      n_flagged: 2,
      by_flag: { stale: 1, circuit_open: 1 },
      rows: [],
    },
    '/qa/retrieval/summary': {
      events: 30,
      hits_by_signal: { structured: 10, dense: 18 },
      hits_by_kind: { subcap: 12 },
      structured_filter_rate: 0.4,
      zero_hit_queries: ['foo'],
      avg_top_score: 0.78,
      avg_k_returned: 8,
    },
    ...overrides,
  };
  globalThis.fetch = vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input.toString();
    for (const [path, body] of Object.entries(defaults)) {
      if (url.includes(path)) {
        return new Response(JSON.stringify(body), { status: 200 });
      }
    }
    return new Response('', { status: 404 });
  }) as unknown as typeof fetch;
}

function renderTile() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <QaHealthTile />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  setupFetch();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('QaHealthTile', () => {
  test('renders the three sections', async () => {
    renderTile();
    expect(await screen.findByText(/QA & Audit/)).toBeInTheDocument();
    expect(screen.getByText(/Your budget/)).toBeInTheDocument();
    expect(screen.getByText(/Source flags/)).toBeInTheDocument();
    expect(screen.getByText(/Retrieval/)).toBeInTheDocument();
  });

  test('shows spend/budget formatted', async () => {
    renderTile();
    expect(await screen.findByText(/\$2\.50 \/ \$5\.00/)).toBeInTheDocument();
    expect(screen.getByText('50% used')).toBeInTheDocument();
  });

  test('flags downgrade when over budget', async () => {
    setupFetch({
      '/qa/budgets/me': {
        user_email: 'alice@zen',
        spend_usd: 7.0,
        budget_usd: 5.0,
        fraction: 1.4,
        should_downgrade: true,
        admin_override: false,
        headroom_usd: 0.0,
      },
    });
    renderTile();
    expect(await screen.findByText(/Pro → Flash/)).toBeInTheDocument();
  });

  test('shows source-flag breakdown', async () => {
    renderTile();
    await screen.findByText(/QA & Audit/);
    await waitFor(() => {
      expect(screen.getByText(/stale:1/)).toBeInTheDocument();
    });
  });

  test('shows retrieval structured rate', async () => {
    renderTile();
    await screen.findByText(/QA & Audit/);
    await waitFor(() => {
      // 0.4 → "40%" rounded
      expect(screen.getByText('40%')).toBeInTheDocument();
    });
  });

  test('healthy fallback when no flags', async () => {
    setupFetch({
      '/qa/source-health/latest': {
        n_sources_seen: 10,
        n_flagged: 0,
        by_flag: {},
        rows: [],
      },
    });
    renderTile();
    await screen.findByText(/QA & Audit/);
    await waitFor(() => {
      expect(screen.getByText('all healthy')).toBeInTheDocument();
    });
  });
});
