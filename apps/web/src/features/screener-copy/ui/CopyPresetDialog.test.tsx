import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { api, TestQueryProvider } from '@/shared/api';
import { expectNoA11yViolations } from '@/shared/lib/testing';

import { CopyPresetDialog } from './CopyPresetDialog';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, api: { POST: vi.fn() } };
});

const POST = vi.mocked(api.POST);

beforeEach(() => {
  POST.mockReset();
});

function setup() {
  const onCopied = vi.fn();
  const onOpenChange = vi.fn();
  const view = render(
    <TestQueryProvider>
      <CopyPresetDialog preset="vrp_scanner" open onOpenChange={onOpenChange} onCopied={onCopied} />
    </TestQueryProvider>,
  );
  return { onCopied, onOpenChange, ...view };
}

describe('CopyPresetDialog', () => {
  it('copies the preset under the chosen name (pinned by the API) and opens the copy', async () => {
    POST.mockResolvedValue({
      data: { screener_id: 'mine', document: {} },
      response: new Response(null, { status: 201 }),
    } as never);
    const { onCopied, baseElement } = setup();
    const name = screen.getByRole('textbox', { name: 'Name of your copy' });
    expect(name).toHaveValue('my-vrp_scanner');
    await expectNoA11yViolations(baseElement);
    await userEvent.clear(name);
    await userEvent.type(name, 'mine');
    await userEvent.click(screen.getByRole('button', { name: 'Copy' }));
    await waitFor(() => {
      expect(onCopied).toHaveBeenCalledWith('mine');
    });
    expect(POST).toHaveBeenCalledWith('/screeners/{screener_id}/copy', {
      params: { path: { screener_id: 'mine' } },
      body: { preset: 'vrp_scanner' },
    });
  });

  it('says when the name is taken, and refuses an invalid one', async () => {
    POST.mockResolvedValue({
      error: { detail: 'u already has a config' },
      response: new Response(null, { status: 409 }),
    } as never);
    const { onCopied } = setup();
    await userEvent.click(screen.getByRole('button', { name: 'Copy' }));
    expect(await screen.findByText('u already has a config')).toBeInTheDocument();
    expect(onCopied).not.toHaveBeenCalled();
    await userEvent.clear(screen.getByRole('textbox', { name: 'Name of your copy' }));
    await userEvent.type(screen.getByRole('textbox', { name: 'Name of your copy' }), 'No Good');
    expect(screen.getByRole('button', { name: 'Copy' })).toBeDisabled();
  });
});
