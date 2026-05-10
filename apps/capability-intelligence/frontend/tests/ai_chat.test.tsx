import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import AiChat from '../src/pages/AiChat';

type Conv = {
  conversation_id: string;
  created_at: string;
  updated_at: string;
  turns: Array<Record<string, unknown>>;
};

const mockResponses: Record<string, unknown> = {
  '/api/chat?limit=50': [
    {
      conversation_id: 'chat-abc12345',
      created_at: '2026-05-10T11:00:00+00:00',
      updated_at: '2026-05-10T11:01:00+00:00',
      turns: [
        { role: 'user', text: 'Hello P1C1.1.1', citations: [], created_at: '2026-05-10T11:00:00+00:00' },
        {
          role: 'assistant',
          text: 'Wells Fargo has an active SOW touching this subcap.',
          citations: ['sow-x'],
          chain_id: 'chain-xyz789',
          cost_usd: 0,
          sources: [
            { id: 'sow-x', kind: 'sow_mention', title: 'SOW Wells Fargo', text: '...' },
          ],
          created_at: '2026-05-10T11:01:00+00:00',
        },
      ],
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

describe('AiChat', () => {
  it('renders conversation list and opens detail with citations + chain link', async () => {
    // Add the per-conversation detail to mocks dynamically
    const list = mockResponses['/api/chat?limit=50'] as Conv[];
    mockResponses['/api/chat/chat-abc12345'] = list[0];

    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <AiChat />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    // Conversation-list row shows last (assistant) turn truncated.
    await waitFor(() =>
      expect(screen.getByText(/Wells Fargo has an active SOW/)).toBeInTheDocument(),
    );
    // Click the list row to open detail.
    const listText = screen.getByText(/Wells Fargo has an active SOW/);
    const listButton = listText.closest('button') as HTMLButtonElement;
    fireEvent.click(listButton);
    // Detail panel renders: assistant text appears full-length (≥1 instance)
    // AND the citation chip "sow-x" + chain backlink are visible.
    await waitFor(
      () => {
        expect(
          screen.getAllByText('Wells Fargo has an active SOW touching this subcap.').length,
        ).toBeGreaterThanOrEqual(1);
        expect(screen.getByText('sow-x')).toBeInTheDocument();
      },
      { timeout: 3000 },
    );
    expect(screen.getByText(/chain xyz789/)).toBeInTheDocument();
  });
});
