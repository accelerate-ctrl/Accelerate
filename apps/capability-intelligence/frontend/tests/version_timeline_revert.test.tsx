// Version Timeline + J11 revert modal (Phase 4.5).

import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import VersionTimeline from '../src/pages/VersionTimeline';

const versions = [
  {
    version_id: 'v-1779100000000000',
    label: 'v1-baseline',
    summary: 'initial seed',
    created_at: '2026-05-01T08:00:00Z',
    created_by: 'admin@zen.co',
    pillar_counts: { P1: 205 },
    is_current: false,
    snapshot_uri: 'repo://snapshots/v1',
    source_files: {},
  },
  {
    version_id: 'v-1779200000000000',
    label: 'v2-current',
    summary: 'mutated',
    created_at: '2026-05-10T08:00:00Z',
    created_by: 'admin@zen.co',
    pillar_counts: { P1: 200 },
    is_current: true,
    snapshot_uri: 'repo://snapshots/v2',
    source_files: {},
  },
];

const preview = {
  target_version_id: 'v-1779100000000000',
  target_label: 'v1-baseline',
  target_created_at: '2026-05-01T08:00:00Z',
  target_created_by: 'admin@zen.co',
  current_subcap_count: 200,
  target_subcap_count: 205,
  added_subcaps: ['P1C3.1.1', 'P1C3.1.2', 'P1C3.1.3', 'P1C3.1.4', 'P1C3.1.5'],
  removed_subcaps: [],
  modified_subcaps: [{ sub_cap_id: 'P1C1.1.1' }],
  pillar_count_deltas: { P1: 5 },
};

let postSpy: ReturnType<typeof vi.fn>;

function setupFetch() {
  postSpy = vi.fn();
  globalThis.fetch = vi.fn().mockImplementation(
    async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString();
      const method = init?.method || 'GET';
      if (method === 'POST') {
        postSpy(url, init?.body);
        return new Response(
          JSON.stringify({
            new_version_id: 'v-revert-1779300000',
            target_version_id: 'v-1779100000000000',
            added: 5,
            removed: 0,
            modified: 1,
            reason: 'audit-test',
            performed_by: 'admin@zen.co',
            performed_at: '2026-05-11T08:00:00Z',
          }),
          { status: 200 },
        );
      }
      if (url.includes('/revert-preview')) {
        return new Response(JSON.stringify(preview), { status: 200 });
      }
      if (url.endsWith('/versions') || url.includes('/versions?')) {
        return new Response(JSON.stringify(versions), { status: 200 });
      }
      return new Response('', { status: 404 });
    },
  ) as unknown as typeof fetch;
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <VersionTimeline />
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

describe('VersionTimeline + revert', () => {
  test('lists versions with revert button only on non-current rows', async () => {
    renderPage();
    await screen.findByText('v1-baseline');
    // Current version is v2; its row should NOT have a revert button.
    expect(
      screen.queryByRole('button', { name: /revert to v-1779200000000000/i }),
    ).not.toBeInTheDocument();
    // v1 is not current → revert button present.
    expect(
      screen.getByRole('button', { name: /revert to v-1779100000000000/i }),
    ).toBeInTheDocument();
  });

  test('opens revert modal and surfaces the preview deltas', async () => {
    renderPage();
    await screen.findByText('v1-baseline');
    fireEvent.click(
      screen.getByRole('button', { name: /revert to v-1779100000000000/i }),
    );
    await screen.findByText(/Revert catalogue to v-1779100000000000/);
    // The preview is fetched asynchronously — wait for the Added
    // count (5) to render.
    await screen.findByText('5');
    // Modified count (1) appears in the same Stat grid.
    expect(screen.getByText('1')).toBeInTheDocument();
  });

  test('commit is disabled until a reason is entered', async () => {
    renderPage();
    await screen.findByText('v1-baseline');
    fireEvent.click(
      screen.getByRole('button', { name: /revert to v-1779100000000000/i }),
    );
    await screen.findByText(/Revert catalogue to v-1779100000000000/);
    // Wait for the preview to load (textarea is gated on preview presence).
    const textarea = await screen.findByPlaceholderText(/Why is the catalogue being reverted/i);
    const commit = (await screen.findByRole('button', { name: /^Revert$/ })) as HTMLButtonElement;
    expect(commit.disabled).toBe(true);
    fireEvent.change(textarea, { target: { value: 'regression in prod' } });
    expect(commit.disabled).toBe(false);
  });

  test('commit posts to the revert endpoint with the reason', async () => {
    renderPage();
    await screen.findByText('v1-baseline');
    fireEvent.click(
      screen.getByRole('button', { name: /revert to v-1779100000000000/i }),
    );
    await screen.findByText(/Revert catalogue to v-1779100000000000/);
    const textarea = await screen.findByPlaceholderText(/Why is the catalogue being reverted/i);
    fireEvent.change(textarea, { target: { value: 'manual rollback' } });
    fireEvent.click(screen.getByRole('button', { name: /^Revert$/ }));
    await waitFor(() => {
      expect(postSpy).toHaveBeenCalledWith(
        expect.stringContaining('/versions/v-1779100000000000/revert'),
        expect.stringContaining('manual rollback'),
      );
    });
  });
});
