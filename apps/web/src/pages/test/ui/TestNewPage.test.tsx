import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { TestNewPage } from './TestNewPage';

vi.mock('@/features/guide-help', () => ({ termHelp: () => null }));
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

describe('TestNewPage', () => {
  it('shows the form and passes its results through', async () => {
    const onCreated = vi.fn();
    const onCancel = vi.fn();
    render(<TestNewPage way="expert" onCreated={onCreated} onCancel={onCancel} />);
    expect(screen.getByRole('heading', { level: 1, name: 'Expert' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'create' }));
    expect(onCreated).toHaveBeenCalledWith('fresh');
    await userEvent.click(screen.getByRole('button', { name: 'cancel' }));
    expect(onCancel).toHaveBeenCalled();
  });

  it('names the Describe it way in', () => {
    render(<TestNewPage way="describe" onCreated={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByRole('heading', { level: 1, name: 'Describe it' })).toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: 'Test steps' })).toHaveTextContent('Describe it');
  });
});
