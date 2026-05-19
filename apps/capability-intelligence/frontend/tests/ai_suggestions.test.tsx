import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import AiSuggestions from '../src/pages/AiSuggestions';

const baseSuggestion = {
  id: 'sug-chain-x-0',
  chain_id: 'chain-abc123',
  sub_cap_id: 'P1C1.1.1',
  kind: 'add_use_case',
  target: 'P1C1.1.1',
  title: 'GenAI strategy doc co-author',
  rationale: 'Three SOWs in active engagements reference an AI assistant.',
  status: 'pending',
  gate_overall: 'warn',
  origin: 'loop',
  created_at: '2026-04-12T08:30:00+00:00',
};

const descriptorSuggestion = {
  id: 'sug-descriptor-1',
  chain_id: 'chain-def',
  sub_cap_id: 'P1C1.1.1',
  kind: 'maturity_descriptor_update',
  target: 'P1C1.1.1',
  title: 'M3 descriptor refresh',
  rationale: 'Add quarterly OKR refresh language.',
  status: 'pending',
  gate_overall: 'pass',
  origin: 'audit',
  created_at: '2026-05-01T08:30:00+00:00',
  proposal_change: {
    level: 'M3',
    current: 'Documented strategy with annual refresh.',
    proposed: 'Documented strategy with quarterly OKR refresh + steering committee.',
  },
};

let postSpy: ReturnType<typeof vi.fn>;

function setupFetch(responses: Record<string, unknown>) {
  postSpy = vi.fn();
  vi.spyOn(globalThis, 'fetch').mockImplementation(
    async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString();
      const method = init?.method || 'GET';
      const path = new URL(url, 'http://localhost').pathname + new URL(url, 'http://localhost').search;
      if (method === 'POST') {
        postSpy(path, init?.body);
        return new Response(
          JSON.stringify({ rejected_count: 2, skipped_count: 0, missing_count: 0 }),
          { status: 200 },
        );
      }
      const body = responses[path];
      if (body === undefined) return new Response('not mocked: ' + path, { status: 404 });
      return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
    },
  );
}

beforeEach(() => {
  setupFetch({
    '/api/suggestions?status=pending': [baseSuggestion],
    '/api/suggestions/stats': { pending: 1, applied: 0, rejected: 0, total: 1 },
    '/api/suggestions/origins': { origins: { loop: 1 } },
  });
});

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <AiSuggestions />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('AiSuggestions', () => {
  it('renders pending suggestions with apply/reject buttons', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText('GenAI strategy doc co-author')).toBeInTheDocument());
    expect(screen.getByText(/Three SOWs in active/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Apply/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^Reject$/ })).toBeInTheDocument();
  });

  it('renders origin chips driven by the origins endpoint', async () => {
    renderPage();
    await screen.findByText('GenAI strategy doc co-author');
    // Origin chip for "loop (1)" is present.
    expect(screen.getByRole('button', { name: /loop \(1\)/ })).toBeInTheDocument();
  });

  it('bulk-selects pending rows and surfaces the toolbar', async () => {
    renderPage();
    const checkbox = await screen.findByRole('checkbox', {
      name: /select suggestion sug-chain-x-0/i,
    });
    fireEvent.click(checkbox);
    expect(screen.getByText(/1 suggestion selected/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Bulk reject/i })).toBeInTheDocument();
  });

  it('bulk-reject modal requires a reason before submit', async () => {
    renderPage();
    const checkbox = await screen.findByRole('checkbox', {
      name: /select suggestion sug-chain-x-0/i,
    });
    fireEvent.click(checkbox);
    fireEvent.click(screen.getByRole('button', { name: /Bulk reject…/i }));
    const submit = (await screen.findByRole('button', {
      name: /^Reject 1$/,
    })) as HTMLButtonElement;
    expect(submit.disabled).toBe(true);
    const textarea = screen.getByPlaceholderText(/Why are these suggestions/i);
    fireEvent.change(textarea, { target: { value: 'low-quality monthly batch' } });
    expect(submit.disabled).toBe(false);
    fireEvent.click(submit);
    await waitFor(() =>
      expect(postSpy).toHaveBeenCalledWith(
        expect.stringContaining('/suggestions/bulk-reject'),
        expect.stringContaining('low-quality monthly batch'),
      ),
    );
  });

  it('renders the maturity descriptor diff for maturity_descriptor_update kind', async () => {
    setupFetch({
      '/api/suggestions?status=pending': [descriptorSuggestion],
      '/api/suggestions/stats': { pending: 1, applied: 0, rejected: 0, total: 1 },
      '/api/suggestions/origins': { origins: { audit: 1 } },
    });
    renderPage();
    await screen.findByText('M3 descriptor refresh');
    // Both Current and Proposed labels appear.
    expect(screen.getByText(/Current · M3/i)).toBeInTheDocument();
    expect(screen.getByText(/Proposed · M3/i)).toBeInTheDocument();
    // The phrase appears in both the rationale and the proposed text —
    // both occurrences are expected.
    expect(screen.getAllByText(/quarterly OKR refresh/i).length).toBeGreaterThanOrEqual(2);
  });
});
