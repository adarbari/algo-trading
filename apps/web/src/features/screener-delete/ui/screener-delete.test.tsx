import { ToastProvider } from '@algotrade/ui';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { api, TestQueryProvider } from '@/shared/api';
import { expectNoA11yViolations } from '@/shared/lib/testing';

import { DeleteScreenerButton } from './DeleteScreenerButton';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, api: { DELETE: vi.fn() } };
});

const DELETE = vi.mocked(api.DELETE);

const setup = (onDeleted = vi.fn()) => {
  const view = render(
    <ToastProvider>
      <TestQueryProvider>
        <DeleteScreenerButton screenerId="my-vrp" onDeleted={onDeleted} />
      </TestQueryProvider>
    </ToastProvider>,
  );
  return { onDeleted, ...view };
};

beforeEach(() => {
  DELETE.mockReset();
});

describe('DeleteScreenerButton', () => {
  it('asks first, then deletes the screener and leaves its pages', async () => {
    DELETE.mockResolvedValue({ response: new Response(null, { status: 204 }) });
    const { onDeleted, baseElement } = setup();
    await userEvent.click(screen.getByRole('button', { name: 'Delete' }));
    const dialog = screen.getByRole('dialog', { name: 'Delete my-vrp?' });
    expect(dialog).toHaveTextContent('stops running nightly');
    await expectNoA11yViolations(baseElement);
    expect(DELETE).not.toHaveBeenCalled();
    await userEvent.click(screen.getAllByRole('button', { name: 'Delete' }).at(-1) as HTMLElement);
    await waitFor(() => {
      expect(onDeleted).toHaveBeenCalled();
    });
    expect(DELETE).toHaveBeenCalledWith('/screeners/{screener_id}', {
      params: { path: { screener_id: 'my-vrp' } },
    });
    expect(await screen.findByText('Deleted my-vrp')).toBeInTheDocument();
  });

  it('cancels without deleting', async () => {
    const { onDeleted } = setup();
    await userEvent.click(screen.getByRole('button', { name: 'Delete' }));
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(DELETE).not.toHaveBeenCalled();
    expect(onDeleted).not.toHaveBeenCalled();
  });

  it('says why a delete failed and stays', async () => {
    DELETE.mockResolvedValue({
      error: { detail: 'no such screen' },
      response: new Response(null, { status: 404, statusText: 'Not Found' }),
    });
    const { onDeleted } = setup();
    await userEvent.click(screen.getByRole('button', { name: 'Delete' }));
    await userEvent.click(screen.getAllByRole('button', { name: 'Delete' }).at(-1) as HTMLElement);
    expect(await screen.findByText('Could not delete the screener')).toBeInTheDocument();
    expect(onDeleted).not.toHaveBeenCalled();
  });
});
