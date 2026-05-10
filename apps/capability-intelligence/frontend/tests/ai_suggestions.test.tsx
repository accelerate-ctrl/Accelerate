import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import AiSuggestions from '../src/pages/AiSuggestions';

const mockResponses: Record<string, unknown> = {
  '/api/suggestions?status=pending': [
    {
      id: 'sug-chain-x-0',
      chain_id: 'chain-abc123',
      sub_cap_id: 'P1C1.1.1',
      kind: 'add_use_case',
      target: 'P1C1.1.1',
      title: 'GenAI strategy doc co-author',
      rationale: 'Three SOWs in active engagements reference an AI assistant.',
      status: 'pending',
      gate_overall: 'warn',
      created_at: '2026-04-12T08:30:00+00:00',
    },
  ],
  '/api/suggestions/stats': { pending: 1, applied: 0, rejected: 0, total: 1 },
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

describe('AiSuggestions', () => {
  it('renders pending suggestions with apply/reject buttons', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <AiSuggestions />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.getByText('GenAI strategy doc co-author')).toBeInTheDocument());
    expect(screen.getByText(/Three SOWs in active/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Apply/ })).toBeInTheDocument();
    // "Reject" button vs the "rejected" filter tab — the action button has capital R + no trailing chars
    expect(screen.getByRole('button', { name: /^Reject$/ })).toBeInTheDocument();
  });
});
