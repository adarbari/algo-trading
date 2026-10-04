import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { ScreenersPage } from './ScreenersPage';

vi.mock('@/widgets/screener-list', async () => {
  const { Button } = await import('@algotrade/ui');
  return {
    ScreenerList: ({ onOpen }: { onOpen: (id: string) => void }) => (
      <Button
        onClick={() => {
          onOpen('my-vrp');
        }}
      >
        open
      </Button>
    ),
  };
});

describe('ScreenersPage', () => {
  it('shows the list with "+ New screener" and passes navigation through', async () => {
    const onOpen = vi.fn();
    const onNew = vi.fn();
    render(<ScreenersPage onOpen={onOpen} onNew={onNew} />);
    expect(screen.getByRole('heading', { level: 1, name: 'Screeners' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '+ New screener' }));
    expect(onNew).toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', { name: 'open' }));
    expect(onOpen).toHaveBeenCalledWith('my-vrp');
  });
});
