import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import SowLibrary from '../src/pages/SowLibrary';

const mockResponses: Record<string, unknown> = {
  '/api/sows': [
    {
      sow_id: 'sow-active-wf',
      file_name: 'Wells_Fargo.txt',
      file_uri: 'file:///x',
      status: 'active',
      source: 'local',
      ingested_at: '2026-01-01',
      client_name: 'Wells Fargo',
      client_confidence: 100,
      page_count: 1,
      char_count: 1234,
      chunk_count: 2,
      mention_count: 5,
      redaction_method: 'regex',
      redaction_summary: { SSN: 1, EMAIL: 2 },
      extractor: 'txt',
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

describe('SowLibrary', () => {
  it('renders the SOW row with redaction summary and mention count', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <SowLibrary />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.getByText('Wells Fargo')).toBeInTheDocument());
    expect(screen.getByText('Wells_Fargo.txt')).toBeInTheDocument();
    expect(screen.getByText(/SSN:1/)).toBeInTheDocument();
    expect(screen.getByText(/5/)).toBeInTheDocument();
  });
});
