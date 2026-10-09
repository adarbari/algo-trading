import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { ScreenersPage } from './ScreenersPage';

vi.mock('@/widgets/screener-list', async () => {
  const { Button } = await import('@algotrade/ui');
  return {
    ScreenerList: ({
      onOpen,
      onEdit,
    }: {
      onOpen: (id: string) => void;
      onEdit: (id: string) => void;
    }) => (
      <>
        <Button
          onClick={() => {
            onOpen('my-vrp');
          }}
        >
          open
        </Button>
        <Button
          onClick={() => {
            onEdit('my-vrp');
          }}
        >
          edit
        </Button>
      </>
    ),
  };
});

describe('ScreenersPage', () => {
  it('shows the list with "+ New screener" and passes navigation through', async () => {
    const onOpen = vi.fn();
    const onEdit = vi.fn();
    const onNew = vi.fn();
    render(
      <ScreenersPage
        onOpen={onOpen}
        onEdit={onEdit}
        onOpenTicker={vi.fn()}
        onOpenEdge={vi.fn()}
        onNew={onNew}
      />,
    );
    expect(screen.getByRole('heading', { level: 1, name: 'Screeners' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '+ New screener' }));
    expect(onNew).toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', { name: 'open' }));
    expect(onOpen).toHaveBeenCalledWith('my-vrp');
    await userEvent.click(screen.getByRole('button', { name: 'edit' }));
    expect(onEdit).toHaveBeenCalledWith('my-vrp');
  });
});
