import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import App from '../src/App';
import { flatEntries, navigation } from '../src/lib/sidebar-config';

function renderApp(initial = '/') {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initial]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('App shell', () => {
  it('renders sidebar with all 9 groups', () => {
    renderApp();
    expect(navigation.length).toBe(9);
    for (const group of navigation) {
      // Group label may match substrings in entries (e.g. "Explore" appears in
      // "Capability Explorer"). Asserting at least one match is enough.
      const matches = screen.queryAllByText((content) => content.includes(group.label));
      expect(matches.length, `group ${group.label} should appear`).toBeGreaterThan(0);
    }
  });

  it('renders all 28 sidebar entries', () => {
    renderApp();
    expect(flatEntries.length).toBe(28);
    for (const entry of flatEntries) {
      // Some entry labels include hyphens / non-ASCII; do partial match
      const matches = screen.queryAllByText((content) => content.startsWith(entry.label));
      expect(matches.length, `entry ${entry.label} should appear`).toBeGreaterThan(0);
    }
  });

  it('renders the header global search', () => {
    renderApp();
    expect(screen.getByLabelText('global search')).toBeInTheDocument();
  });

  it('home route lands on Mission Control', () => {
    renderApp('/');
    // Mission Control text appears in both sidebar nav AND page heading.
    expect(screen.getAllByText('Mission Control').length).toBeGreaterThanOrEqual(2);
  });
});
