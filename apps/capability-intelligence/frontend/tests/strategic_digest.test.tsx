import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import StrategicDigest from '../src/pages/StrategicDigest';

const mockResponses: Record<string, unknown> = {
  '/api/digest?limit=50': [
    {
      digest_id: 'digest-retail-banking-2026-Q2',
      subvertical: 'retail-banking',
      period: '2026-Q2',
      previous_period: '2026-Q1',
      generated_at: '2026-05-10T12:00:00+00:00',
      model: 'opus',
      summary: 'Q2 2026 summary',
      sources_count: 9,
      total_cost_usd: 0.0,
      priorities: [],
    },
  ],
  '/api/digest/digest-retail-banking-2026-Q2': {
    digest_id: 'digest-retail-banking-2026-Q2',
    subvertical: 'retail-banking',
    period: '2026-Q2',
    previous_period: '2026-Q1',
    generated_at: '2026-05-10T12:00:00+00:00',
    model: 'opus',
    summary: 'Q2 2026 summary paragraph',
    sources_count: 9,
    total_cost_usd: 0.0,
    priorities: [
      {
        sub_cap_id: 'P1C1.1.1',
        sub_cap_name: 'Digital Strategy Document',
        state: 'RISING',
        score: 78.5,
        confidence: 0.75,
        narrative: 'Demand signal strong across SOWs and analyst commentary.',
        recommendation: 'Schedule a Q3 deep-dive review.',
        evidence_sows: [{ sow_id: 'sow-1', client: 'Wells Fargo', status: 'active', excerpt: 'covering digital strategy' }],
        evidence_benchmarks: [{ metric_id: 'tech_spend_pct_revenue', cohort_id: 'us_banks_gsib', verdict: 'INDICATIVE', p50: 11.6 }],
        evidence_news: [{ id: 'n1', title: 'GenAI strategy', source: 'americanbanker.com', kind: 'news', url: null }],
        delta: { previous_state: 'EMERGING', previous_period: '2026-Q1' },
        chain_id: 'chain-abc12345',
        cost_usd: 0,
      },
    ],
  },
};

beforeEach(() => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input.toString();
    const path = new URL(url, 'http://localhost').pathname + new URL(url, 'http://localhost').search;
    const body = mockResponses[path] ?? mockResponses[path.split('?')[0]];
    if (body === undefined) return new Response('not mocked: ' + path, { status: 404 });
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
  });
});

describe('StrategicDigest', () => {
  it('renders digest list + opens detail with priority cards', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <StrategicDigest />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    // Wait for the digest list item to render — period appears in the row
    await waitFor(() => expect(screen.getAllByText('2026-Q2').length).toBeGreaterThanOrEqual(1));
    // Click the digest-row button — the row contains a font-mono period span.
    const periodSpans = screen.getAllByText('2026-Q2');
    const listRow = periodSpans
      .map((el) => el.closest('button'))
      .find(Boolean) as HTMLButtonElement | undefined;
    expect(listRow).toBeTruthy();
    fireEvent.click(listRow!);
    await waitFor(() =>
      expect(screen.getByText('Digital Strategy Document')).toBeInTheDocument(),
    );
    // RISING appears multiple times (state badge + delta arrow target) — assert ≥1
    expect(screen.getAllByText('RISING').length).toBeGreaterThanOrEqual(1);
    expect(
      screen.getByText(/Demand signal strong across SOWs/),
    ).toBeInTheDocument();
    // Q-over-Q delta — EMERGING text appears in the from-state span
    expect(screen.getByText('EMERGING')).toBeInTheDocument();
  });
});
