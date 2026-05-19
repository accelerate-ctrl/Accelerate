// CascadePreviewModal — covers the J4 approval gate behavior.

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';
import CascadePreviewModal from '@/components/CascadePreviewModal';

const baseReport = {
  sub_cap_id: 'P1C1.1.1',
  sub_cap_name: 'Strategy Definition',
  from_status: 'Active',
  to_status: 'Inactive',
  reason: null,
  targets: [
    { label: 'User stories', collection: 'stories', count: 3, sample_ids: ['S1', 'S2', 'S3'] },
    { label: 'L4 features', collection: 'l4_features', count: 2, sample_ids: ['F1', 'F2'] },
  ],
  total_rows_affected: 5,
  applied: false,
  run_id: null,
};

function mockFetchPreview() {
  globalThis.fetch = vi.fn().mockImplementation(async (url: string) => {
    if (typeof url === 'string' && url.includes('/cascade/preview/')) {
      return new Response(JSON.stringify(baseReport), { status: 200 });
    }
    if (typeof url === 'string' && url.includes('/cascade/apply/')) {
      return new Response(
        JSON.stringify({ ...baseReport, applied: true, run_id: 'cascade-abc', reason: 'Test' }),
        { status: 200 },
      );
    }
    return new Response('', { status: 404 });
  }) as unknown as typeof fetch;
}

beforeEach(() => {
  mockFetchPreview();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('CascadePreviewModal', () => {
  test('renders preview with downstream impact', async () => {
    render(<CascadePreviewModal subCapId="P1C1.1.1" onCancel={() => {}} />);
    expect(await screen.findByText('Strategy Definition')).toBeInTheDocument();
    expect(screen.getByText('5 rows')).toBeInTheDocument();
    expect(screen.getByText('User stories')).toBeInTheDocument();
    expect(screen.getByText('L4 features')).toBeInTheDocument();
  });

  test('deactivate button is disabled until reason is entered', async () => {
    render(<CascadePreviewModal subCapId="P1C1.1.1" onCancel={() => {}} />);
    const btn = (await screen.findByRole('button', { name: /^deactivate$/i })) as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
    const textarea = screen.getByPlaceholderText(/why is this subcap/i);
    fireEvent.change(textarea, { target: { value: 'Test reason' } });
    expect(btn.disabled).toBe(false);
  });

  test('commit calls onApplied with the applied report', async () => {
    const onApplied = vi.fn();
    render(
      <CascadePreviewModal subCapId="P1C1.1.1" onCancel={() => {}} onApplied={onApplied} />,
    );
    await screen.findByText('Strategy Definition');
    fireEvent.change(screen.getByPlaceholderText(/why is this subcap/i), {
      target: { value: 'rolling back a stale subcap' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^deactivate$/i }));
    await waitFor(() => expect(onApplied).toHaveBeenCalled());
    expect(onApplied.mock.calls[0][0].applied).toBe(true);
    expect(onApplied.mock.calls[0][0].run_id).toBe('cascade-abc');
  });

  test('cancel triggers onCancel without applying', async () => {
    const onCancel = vi.fn();
    render(<CascadePreviewModal subCapId="P1C1.1.1" onCancel={onCancel} />);
    await screen.findByText('Strategy Definition');
    fireEvent.click(screen.getByRole('button', { name: /^cancel$/i }));
    expect(onCancel).toHaveBeenCalled();
  });

  test('reactivate variant changes the verb', async () => {
    render(<CascadePreviewModal subCapId="P1C1.1.1" toStatus="Active" onCancel={() => {}} />);
    expect(await screen.findByRole('button', { name: /^reactivate$/i })).toBeInTheDocument();
  });
});
