import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import ValueChainAtlas from '../src/pages/ValueChainAtlas';

const mockResponses: Record<string, unknown> = {
  '/api/lens/subverticals': [
    { code: 'RB', name: 'Retail Banking' },
    { code: 'CU', name: 'Credit Unions' },
  ],
  '/api/lens/value-chain-atlas': {
    subvertical_code: null,
    clusters: [
      {
        code: 'VCC-01',
        name: 'MARKET',
        color: '#1c4a4d',
        total_subcaps: 50,
        stages: [{ name: 'MARKET', subvertical_code: 'RB', subcap_count: 30, subcap_ids: [] }],
      },
      { code: 'VCC-08', name: 'OPERATE & PLATFORM', color: '#1c4a4d', total_subcaps: 30, stages: [] },
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

describe('ValueChainAtlas', () => {
  it('renders 2 cluster cards with stage detail', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <ValueChainAtlas />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.getByText('VCC-01')).toBeInTheDocument());
    // 'MARKET' appears as both cluster name AND stage label; getAll handles both.
    expect(screen.getAllByText('MARKET').length).toBeGreaterThan(0);
    expect(screen.getByText('OPERATE & PLATFORM')).toBeInTheDocument();
  });
});
