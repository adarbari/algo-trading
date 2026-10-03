import { ToastProvider } from '@algotrade/ui';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { api, TestQueryProvider } from '@/shared/api';

import { saveTextFile } from '../lib/save-file';
import { DownloadItemsButton } from './DownloadItemsButton';

vi.mock('@/shared/api', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  api: { GET: vi.fn() },
}));
vi.mock('../lib/save-file', () => ({ saveTextFile: vi.fn() }));

function renderButton(runId: string | null) {
  return render(
    <ToastProvider>
      <TestQueryProvider>
        <DownloadItemsButton runId={runId} />
      </TestQueryProvider>
    </ToastProvider>,
  );
}

describe('DownloadItemsButton', () => {
  it('saves the run items as CSV and confirms', async () => {
    vi.mocked(api.GET).mockResolvedValue({
      data: [{ key: 'AAPL', code: 'OK', status: 'OK' }],
      response: new Response(null, { status: 200 }),
    });
    renderButton('option_chains-2026-10-02');
    await userEvent.click(screen.getByRole('button', { name: 'Download items (CSV)' }));
    expect(await screen.findByText('1 items saved')).toBeInTheDocument();
    expect(saveTextFile).toHaveBeenCalledWith(
      'option_chains-2026-10-02-items.csv',
      'key,code,status\nAAPL,OK,OK\n',
    );
  });

  it('reports a failed download', async () => {
    vi.mocked(api.GET).mockResolvedValue({
      error: { detail: 'no run' },
      response: new Response(null, { status: 404 }),
    });
    renderButton('r1');
    await userEvent.click(screen.getByRole('button', { name: 'Download items (CSV)' }));
    expect(await screen.findByText('The items could not be downloaded')).toBeInTheDocument();
  });

  it('is disabled without a run', () => {
    renderButton(null);
    expect(screen.getByRole('button', { name: 'Download items (CSV)' })).toBeDisabled();
  });
});
