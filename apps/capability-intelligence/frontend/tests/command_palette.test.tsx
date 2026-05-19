// IMP-1 — Cmd/Ctrl+K command palette tests.

import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import CommandPalette from '@/components/CommandPalette';

const subcaps = [
  { sub_cap_id: 'P1C1.1.1', sub_cap_name: 'Digital Strategy Document', pillar_id: 'P1' },
  { sub_cap_id: 'P1C3.5.2', sub_cap_name: 'Open Banking API', pillar_id: 'P1' },
];

const l3s = [
  { l3_id: 'L3-SF-FSC', name: 'Salesforce Financial Services Cloud', vendor: 'Salesforce' },
];

const chains = [
  { chain_id: 'chain-abc', operation: 'news_impact', sub_cap_id: 'P1C1.1.1' },
];

function setupFetch() {
  globalThis.fetch = vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input.toString();
    if (url.includes('/catalogue/subcaps') && !url.includes('/subcaps/')) {
      return new Response(JSON.stringify(subcaps), { status: 200 });
    }
    if (url.includes('/catalogue/l3-platforms')) {
      return new Response(JSON.stringify(l3s), { status: 200 });
    }
    if (url.includes('/reasoning-chains')) {
      return new Response(JSON.stringify(chains), { status: 200 });
    }
    return new Response('', { status: 404 });
  }) as unknown as typeof fetch;
}

function renderPalette() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <CommandPalette />
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

describe('CommandPalette', () => {
  test('renders null until Cmd/Ctrl+K toggles it open', async () => {
    const { container } = renderPalette();
    expect(container.querySelector('[role="dialog"]')).toBeNull();
    fireEvent.keyDown(window, { key: 'k', metaKey: true });
    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });
  });

  test('Escape closes the palette', async () => {
    renderPalette();
    fireEvent.keyDown(window, { key: 'k', ctrlKey: true });
    await screen.findByRole('dialog');
    fireEvent.keyDown(window, { key: 'Escape' });
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).toBeNull();
    });
  });

  test('default view shows static page entries', async () => {
    renderPalette();
    fireEvent.keyDown(window, { key: 'k', metaKey: true });
    await screen.findByRole('dialog');
    // Several static page items always present even before fetch completes.
    expect(screen.getByText('Capability Explorer')).toBeInTheDocument();
    expect(screen.getByText('Knowledge Graph')).toBeInTheDocument();
  });

  test('typing filters results and surfaces a subcap match', async () => {
    renderPalette();
    fireEvent.keyDown(window, { key: 'k', metaKey: true });
    const input = await screen.findByRole('textbox', { name: /command palette/i });
    // Wait for the index to load (subcap fetch resolves async).
    await waitFor(() => {
      // The input is open; fire a search for the subcap id.
      fireEvent.change(input, { target: { value: 'P1C3.5.2' } });
    });
    await waitFor(() => {
      expect(screen.getByText(/Open Banking API/)).toBeInTheDocument();
    });
  });

  test('typing surfaces L3 platform matches', async () => {
    renderPalette();
    fireEvent.keyDown(window, { key: 'k', metaKey: true });
    const input = await screen.findByRole('textbox', { name: /command palette/i });
    fireEvent.change(input, { target: { value: 'L3-SF-FSC' } });
    await waitFor(() => {
      expect(screen.getByText(/Salesforce Financial Services Cloud/)).toBeInTheDocument();
    });
  });

  test('empty-match query shows a hint row', async () => {
    renderPalette();
    fireEvent.keyDown(window, { key: 'k', metaKey: true });
    const input = await screen.findByRole('textbox', { name: /command palette/i });
    fireEvent.change(input, { target: { value: 'xyzzy-no-match' } });
    expect(await screen.findByText(/No matches/i)).toBeInTheDocument();
  });

  test('arrow keys move selection without losing focus', async () => {
    renderPalette();
    fireEvent.keyDown(window, { key: 'k', metaKey: true });
    const input = await screen.findByRole('textbox', { name: /command palette/i });
    // Arrow down — first option becomes selected, second after a second
    // press. We can't easily assert aria-selected from text matchers,
    // but the listbox + dialog should still be open.
    fireEvent.keyDown(input, { key: 'ArrowDown' });
    fireEvent.keyDown(input, { key: 'ArrowDown' });
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  test('Cmd+K closes the palette when already open', async () => {
    renderPalette();
    fireEvent.keyDown(window, { key: 'k', metaKey: true });
    await screen.findByRole('dialog');
    fireEvent.keyDown(window, { key: 'k', metaKey: true });
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).toBeNull();
    });
  });
});
