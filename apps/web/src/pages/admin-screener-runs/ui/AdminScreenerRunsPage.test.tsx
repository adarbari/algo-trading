import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { AdminScreenerRunsPage } from './AdminScreenerRunsPage';

vi.mock('@/widgets/screener-run-list', () => ({
  ScreenerRunList: ({ selected }: { selected: string | null }) => `[list ${selected ?? 'none'}]`,
}));
vi.mock('@/widgets/screener-run-detail', () => ({
  ScreenerRunDetail: ({ id }: { id: string | null }) => `[detail ${id ?? 'none'}]`,
}));

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('AdminScreenerRunsPage', () => {
  it('lays out the list and the detail and passes the chosen run down', () => {
    render(<AdminScreenerRunsPage selected="r1" onSelect={vi.fn()} onClear={vi.fn()} />);
    expect(screen.getByRole('heading', { level: 1, name: 'Screener runs' })).toBeInTheDocument();
    expect(document.body).toHaveTextContent('[list r1]');
    expect(document.body).toHaveTextContent('[detail r1]');
  });

  it('on a phone the detail opens in a sheet only once a run is chosen, and closing clears it', async () => {
    vi.stubGlobal('innerWidth', 375);
    const onClear = vi.fn();
    const props = { onSelect: vi.fn(), onClear };
    const { rerender } = render(<AdminScreenerRunsPage {...props} />);
    expect(screen.queryByText('[detail r1]')).not.toBeInTheDocument();
    rerender(<AdminScreenerRunsPage selected="r1" {...props} />);
    expect(await screen.findByText('[detail r1]')).toBeInTheDocument();
    await userEvent.keyboard('{Escape}');
    expect(onClear).toHaveBeenCalled();
  });
});
