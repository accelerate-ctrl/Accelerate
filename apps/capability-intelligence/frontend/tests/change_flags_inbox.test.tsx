// Change Flags Inbox — J5 approval-gate UI.

import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';
import {
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import ChangeFlagsInbox from '../src/pages/ChangeFlagsInbox';

const baseFlag = {
  flag_id: 'flag-aix',
  kind: 'AI_PROPOSED_EDGE',
  severity: 'MEDIUM' as const,
  target_type: 'subcap',
  target_id: 'P1C1.1.1',
  title: 'Layer-B edge proposal',
  detail: 'SEMANTICALLY_SIMILAR with cosine 0.91',
  detected_at: '2026-05-01T08:00:00Z',
};

const secondFlag = {
  flag_id: 'flag-high',
  kind: 'SCHEMA_INCOMPLETE',
  severity: 'HIGH' as const,
  target_type: 'pillar',
  target_id: 'P2',
  title: 'Schema gap',
  detail: 'tab 17 missing',
  detected_at: '2026-05-02T08:00:00Z',
};

const postSpy = vi.fn();

function setupFetch(opts?: { reject?: boolean }) {
  postSpy.mockReset();
  globalThis.fetch = vi
    .fn()
    .mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString();
      const method = init?.method || 'GET';
      if (method === 'GET') {
        if (url.includes('/flags/_kinds')) {
          return new Response(
            JSON.stringify({
              kinds: { AI_PROPOSED_EDGE: 1, SCHEMA_INCOMPLETE: 1 },
              severities: { MEDIUM: 1, HIGH: 1 },
              total: 2,
            }),
            { status: 200 },
          );
        }
        if (url.includes('/flags')) {
          // Honor severity filter in the URL so the test for filtering can pass.
          if (url.includes('severity=HIGH')) {
            return new Response(JSON.stringify([secondFlag]), { status: 200 });
          }
          return new Response(JSON.stringify([baseFlag, secondFlag]), {
            status: 200,
          });
        }
      } else if (method === 'POST') {
        postSpy(url, init?.body);
        if (opts?.reject) {
          return new Response('rejected', { status: 422 });
        }
        return new Response(
          JSON.stringify({
            ...baseFlag,
            disposition: 'approved',
            resolved_at: '2026-05-03T08:00:00Z',
          }),
          { status: 200 },
        );
      }
      return new Response('', { status: 404 });
    }) as unknown as typeof fetch;
}

function renderInbox() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ChangeFlagsInbox />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  setupFetch();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('ChangeFlagsInbox', () => {
  test('renders flag rows', async () => {
    renderInbox();
    expect(await screen.findByText('Layer-B edge proposal')).toBeInTheDocument();
    expect(screen.getByText('Schema gap')).toBeInTheDocument();
  });

  test('approve button posts to /approve endpoint', async () => {
    renderInbox();
    await screen.findByText('Layer-B edge proposal');
    const approveButtons = screen.getAllByRole('button', { name: /approve/i });
    fireEvent.click(approveButtons[0]);
    await waitFor(() =>
      expect(postSpy).toHaveBeenCalledWith(
        expect.stringContaining('/flags/flag-aix/approve'),
        expect.any(String),
      ),
    );
  });

  test('defer button posts to /defer endpoint', async () => {
    renderInbox();
    await screen.findByText('Layer-B edge proposal');
    const buttons = screen.getAllByRole('button', { name: /defer/i });
    fireEvent.click(buttons[0]);
    await waitFor(() =>
      expect(postSpy).toHaveBeenCalledWith(
        expect.stringContaining('/flags/flag-aix/defer'),
        expect.any(String),
      ),
    );
  });

  test('reject opens modal and submits with reason', async () => {
    renderInbox();
    await screen.findByText('Layer-B edge proposal');
    const rejectButtons = screen.getAllByRole('button', { name: /^reject flag$/i });
    fireEvent.click(rejectButtons[0]);
    // Modal appears
    const textarea = await screen.findByPlaceholderText(/why is this flag/i);
    // Submit disabled until non-empty reason
    const submitBtn = screen.getByRole('button', { name: /^reject$/i });
    expect((submitBtn as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(textarea, { target: { value: 'duplicate edge' } });
    expect((submitBtn as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(submitBtn);
    await waitFor(() =>
      expect(postSpy).toHaveBeenCalledWith(
        expect.stringContaining('/flags/flag-aix/reject'),
        expect.stringContaining('duplicate edge'),
      ),
    );
  });

  test('severity filter narrows the list', async () => {
    renderInbox();
    await screen.findByText('Layer-B edge proposal');
    // Click HIGH chip
    const highChip = screen.getByRole('button', { name: /^HIGH/ });
    fireEvent.click(highChip);
    // After filter, the MEDIUM flag is removed and only the HIGH flag remains.
    await waitFor(() => {
      expect(
        screen.queryByText('Layer-B edge proposal'),
      ).not.toBeInTheDocument();
    });
    // The HIGH flag should still render via the filtered re-fetch.
    await waitFor(() => {
      expect(screen.getByText('Schema gap')).toBeInTheDocument();
    });
  });
});
