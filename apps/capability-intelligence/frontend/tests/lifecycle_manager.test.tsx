import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import LifecycleManager from '../src/pages/LifecycleManager';

const mockResponses: Record<string, unknown> = {
  '/api/lifecycle?limit=2000': [
    {
      sub_cap_id: 'P1C1.1.1',
      sub_cap_name: 'Digital Strategy Document',
      state: 'RISING',
      score: 78.5,
      confidence: 0.75,
      signals: {
        sow_active: 2, sow_prospect: 1, sow_inactive: 0, sow_archived: 0,
        sow_recency_days: 14,
        canonical_stories: 8, jira_stories: 0,
        news_last_90d: 2, news_recency_days: 12,
        trends_last_90d: 1,
        benchmark_indicative: 1, benchmark_full: 0, benchmark_exploratory: 0,
        ai_extrapolations: 0,
      },
      last_signal_at: '2026-04-12T08:30:00+00:00',
      computed_at: '2026-05-10T11:00:00+00:00',
    },
    {
      sub_cap_id: 'P1C2.7.1',
      sub_cap_name: 'Regulatory Change Management',
      state: 'STABLE',
      score: 56.0,
      confidence: 0.5,
      signals: {
        sow_active: 1, sow_prospect: 0, sow_inactive: 0, sow_archived: 0,
        sow_recency_days: 30,
        canonical_stories: 10, jira_stories: 0,
        news_last_90d: 1, news_recency_days: 25,
        trends_last_90d: 1,
        benchmark_indicative: 0, benchmark_full: 0, benchmark_exploratory: 0,
        ai_extrapolations: 0,
      },
      last_signal_at: '2026-03-22T14:00:00+00:00',
      computed_at: '2026-05-10T11:00:00+00:00',
    },
  ],
  '/api/lifecycle/transitions?limit=20': [
    {
      id: 'trans-P1C1.1.1-1234',
      sub_cap_id: 'P1C1.1.1',
      from_state: 'EMERGING',
      to_state: 'RISING',
      score: 78.5,
      transitioned_at: '2026-05-10T10:00:00+00:00',
    },
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

describe('LifecycleManager', () => {
  it('groups subcaps into kanban columns by state + shows transitions', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <LifecycleManager />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    // 6 column headers always render
    await waitFor(() => expect(screen.getByText('Rising')).toBeInTheDocument());
    expect(screen.getByText('Stable')).toBeInTheDocument();
    expect(screen.getByText('Emerging')).toBeInTheDocument();
    expect(screen.getByText('Dead')).toBeInTheDocument();
    // Both subcap IDs render in their columns (font-mono spans)
    await waitFor(() => expect(screen.getAllByText('P1C1.1.1').length).toBeGreaterThanOrEqual(1));
    expect(screen.getByText('P1C2.7.1')).toBeInTheDocument();
    // Transitions section
    expect(screen.getByText(/Recent transitions/i)).toBeInTheDocument();
  });
});
