import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import NewsWatch from '../src/pages/NewsWatch';

const mockResponses: Record<string, unknown> = {
  '/api/news?limit=200': [
    {
      id: 'news-abc',
      url: 'https://www.americanbanker.com/x',
      title: 'Wells Fargo accelerates GenAI strategy',
      text: 'Wells Fargo rolls out GenAI digital strategy authoring (P1C1.1.1).',
      source: 'americanbanker.com',
      published_at: '2026-04-12T08:30:00+00:00',
      ingested_at: '2026-04-12T09:00:00+00:00',
      kind: 'news',
      subverticals: ['retail-banking'],
      sub_cap_hits: ['P1C1.1.1'],
    },
  ],
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

describe('NewsWatch', () => {
  it('renders news items with subcap hits + subverticals', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <NewsWatch />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.getByText(/Wells Fargo accelerates/i)).toBeInTheDocument());
    expect(screen.getByText('americanbanker.com')).toBeInTheDocument();
    expect(screen.getByText('P1C1.1.1')).toBeInTheDocument();
    expect(screen.getByText('retail-banking')).toBeInTheDocument();
  });

  it('renders per-subcap magnitude chips when impact carries affected_subcaps', async () => {
    mockResponses['/api/news?limit=200'] = [
      {
        id: 'news-mag',
        url: 'https://occ.gov/news/x',
        title: 'OCC publishes open-banking rule',
        text: 'OCC publishes a rule on open banking.',
        source: 'occ.gov',
        published_at: '2026-05-18T08:00:00+00:00',
        ingested_at: '2026-05-18T09:00:00+00:00',
        kind: 'news',
        subverticals: ['retail-banking'],
        sub_cap_hits: ['P1C3.5.2'],
        impact: {
          summary: 'Direct regulator action on open banking',
          impact_class: 'catalogue_extension',
          affected_subcaps: [
            { sub_cap_id: 'P1C3.5.2', magnitude: 'HIGH', rationale: 'Direct rule' },
            { sub_cap_id: 'P1C2.1.1', magnitude: 'MEDIUM', rationale: 'Governance' },
          ],
          confidence: 0.9,
          synthesised_at: '2026-05-18T10:00:00+00:00',
        },
      },
    ];
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <NewsWatch />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await waitFor(() =>
      expect(screen.getByText(/OCC publishes/i)).toBeInTheDocument(),
    );
    // Magnitude chips render alongside their subcap ids.
    expect(screen.getByText('HIGH')).toBeInTheDocument();
    expect(screen.getByText('MEDIUM')).toBeInTheDocument();
    expect(screen.getByText('P1C3.5.2')).toBeInTheDocument();
    expect(screen.getByText('P1C2.1.1')).toBeInTheDocument();
  });
});
