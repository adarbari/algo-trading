import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { TestStartPage } from './TestStartPage';

vi.mock('@/features/guide-help', () => ({ termHelp: () => null }));
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

describe('TestStartPage', () => {
  it('offers the ways in as cards, shows the list and passes navigation through', async () => {
    const onOpen = vi.fn();
    const onEdit = vi.fn();
    const onChoose = vi.fn();
    render(
      <TestStartPage
        onOpen={onOpen}
        onEdit={onEdit}
        onOpenEdge={vi.fn()}
        onChoose={onChoose}
        search={{}}
        onSearchChange={vi.fn()}
      />,
    );
    expect(screen.getByRole('heading', { level: 1, name: 'Test' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /^Guided/ }));
    await userEvent.click(screen.getByRole('button', { name: /^Expert/ }));
    await userEvent.click(screen.getByRole('button', { name: /^Describe it/ }));
    expect(onChoose.mock.calls).toEqual([['guided'], ['expert'], ['describe']]);
    await userEvent.click(screen.getByRole('button', { name: 'open' }));
    expect(onOpen).toHaveBeenCalledWith('my-vrp');
    await userEvent.click(screen.getByRole('button', { name: 'edit' }));
    expect(onEdit).toHaveBeenCalledWith('my-vrp');
  });
});
