import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import MaturityHeatmap from '../src/pages/MaturityHeatmap';

const mockResponses: Record<string, unknown> = {
  '/api/catalogue/pillars': [{ pillar_id: 'P1', name: 'Strategic', schema_status: 'complete' }],
  '/api/lens/cohorts': [],
  '/api/lens/maturity-heatmap?pillar_id=P1&sort=category': {
    pillar_id: 'P1',
    cohort_id: null,
    cohort_observations: 0,
    sort: 'category',
    levels: ['M1', 'M2', 'M3', 'M4', 'M5'],
    bands: [
      { key: 'activating', label: 'Activating', tier_range: [1, 1] },
      { key: 'building', label: 'Building', tier_range: [2, 2] },
      { key: 'competing', label: 'Competing', tier_range: [3, 3] },
      { key: 'differentiating', label: 'Differentiating', tier_range: [4, 5] },
    ],
    rows: [
      {
        sub_cap_id: 'P1C1.1.1',
        sub_cap_name: 'Digital Strategy Document',
        category_id: 'P1C1',
        l1_capability: 'Strategy Foundation & Alignment',
        current_level: 5,
        benchmark_level: null,
        gap: null,
        zds_band: 'differentiating',
        cells: [
          { level: 'M1', filled: true, preview: 'Doc-based' },
          { level: 'M2', filled: true, preview: 'In FSC' },
          { level: 'M3', filled: true, preview: 'Data-grounded' },
          { level: 'M4', filled: false, preview: '' },
          { level: 'M5', filled: true, preview: 'Headless 360' },
        ],
      },
    ],
  },
};

beforeEach(() => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input.toString();
    const path = new URL(url, 'http://localhost').pathname + new URL(url, 'http://localhost').search;
    const body = mockResponses[path];
    if (body === undefined) return new Response('not mocked: ' + path, { status: 404 });
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
  });
});

describe('MaturityHeatmap', () => {
  it('renders a row for each subcap with M1..M5 cells', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <MaturityHeatmap />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.getByText('Digital Strategy Document')).toBeInTheDocument());
    expect(screen.getByText('M1')).toBeInTheDocument();
    expect(screen.getByText('M5')).toBeInTheDocument();
  });
});
