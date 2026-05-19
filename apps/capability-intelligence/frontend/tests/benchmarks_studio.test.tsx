import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import BenchmarksStudio from '../src/pages/BenchmarksStudio';

const mockResponses: Record<string, unknown> = {
  '/api/benchmarks/metrics': [
    { metric_id: 'tech_spend_pct_revenue', name: 'Technology spend as % of revenue', unit: '%' },
  ],
  '/api/benchmarks/cohorts': [
    { cohort_id: 'us_banks_gsib', name: 'US banks — GSIB' },
  ],
  '/api/benchmarks': [
    {
      id: 'dist-tech_spend_pct_revenue-us_banks_gsib-2025-Q4',
      metric_id: 'tech_spend_pct_revenue',
      cohort_id: 'us_banks_gsib',
      period: '2025-Q4',
      n: 8,
      effective_n: 4,
      min: 10.8,
      max: 12.1,
      mean: 11.37,
      stdev: 0.55,
      cluster_aware_mean: 11.4,
      cluster_aware_stdev: 0.62,
      p25: 11.0,
      p50: 11.2,
      p75: 11.65,
      coef_var: 0.05,
      ci_low: 10.95,
      ci_high: 11.55,
      ci_method: 'hierarchical-bootstrap',
      ci_level: 0.9,
      verdict: 'INDICATIVE',
      source_kinds: ['filing'],
      observation_ids: [],
      computed_at: '2026-05-10T10:00:00+00:00',
    },
  ],
  '/api/benchmarks/sources': [
    { id: 'src-10-k', label: '10-K', kind: 'filing', tier: 'T1', observation_count: 11, url: null },
  ],
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

describe('BenchmarksStudio', () => {
  function renderPage() {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <BenchmarksStudio />
        </MemoryRouter>
      </QueryClientProvider>,
    );
  }

  it('renders distribution row with verdict badge + percentile labels', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText('INDICATIVE')).toBeInTheDocument());
    // metric label appears both in dropdown <option> and the row title — match the row span.
    expect(screen.getAllByText(/Technology spend as % of revenue/).length).toBeGreaterThanOrEqual(1);
    // cohort label appears in dropdown + row.
    expect(screen.getAllByText('US banks — GSIB').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('11.20')).toBeInTheDocument(); // p50
    expect(screen.getByText('10-K')).toBeInTheDocument();
  });

  it('renders the hierarchical bootstrap CI band + effective_n + cluster_aware_stdev (F06)', async () => {
    renderPage();
    await screen.findByText('INDICATIVE');
    // CI numerals appear inline (10.95–11.55).
    expect(screen.getByText('10.95–11.55')).toBeInTheDocument();
    // effective_n badge: 4/8.
    expect(screen.getByText('4')).toBeInTheDocument();
    // cluster-aware stdev: σ_cluster 0.62.
    expect(screen.getByText('0.62')).toBeInTheDocument();
  });
});
