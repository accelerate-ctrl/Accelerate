import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import App from '../src/App';
import { flatEntries } from '../src/lib/sidebar-config';

describe('routing — every nav entry resolves to a page stub', () => {
  for (const entry of flatEntries) {
    it(`route ${entry.path} renders ${entry.label}`, () => {
      const qc = new QueryClient();
      render(
        <QueryClientProvider client={qc}>
          <MemoryRouter initialEntries={[entry.path]}>
            <App />
          </MemoryRouter>
        </QueryClientProvider>,
      );
      // Page heading for the stub
      expect(
        screen.getAllByText(entry.label).length,
        `${entry.path} should show heading "${entry.label}"`,
      ).toBeGreaterThan(0);
    });
  }
});
