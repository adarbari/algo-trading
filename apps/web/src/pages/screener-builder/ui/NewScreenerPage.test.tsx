import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { NewScreenerPage } from './NewScreenerPage';

vi.mock('@/features/screener-builder', async () => {
  const { Button } = await import('@algotrade/ui');
  return {
    NewScreenerForm: ({
      onCreated,
      onCancel,
    }: {
      onCreated: (id: string) => void;
      onCancel: () => void;
    }) => (
      <>
        <Button
          onClick={() => {
            onCreated('fresh');
          }}
        >
          create
        </Button>
        <Button onClick={onCancel}>cancel</Button>
      </>
    ),
  };
});

describe('NewScreenerPage', () => {
  it('shows the form and passes its results through', async () => {
    const onCreated = vi.fn();
    const onCancel = vi.fn();
    render(<NewScreenerPage onCreated={onCreated} onCancel={onCancel} />);
    expect(screen.getByRole('heading', { level: 1, name: 'New screener' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'create' }));
    expect(onCreated).toHaveBeenCalledWith('fresh');
    await userEvent.click(screen.getByRole('button', { name: 'cancel' }));
    expect(onCancel).toHaveBeenCalled();
  });
});
