import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { AdminHarnessRunsPage } from './AdminHarnessRunsPage';

vi.mock('@/widgets/harness-run-list', () => ({
  HarnessRunList: ({ selected }: { selected: string | null }) => `[list ${selected ?? 'none'}]`,
}));
vi.mock('@/widgets/harness-run-detail', () => ({
  HarnessRunDetail: ({ id }: { id: string | null }) => `[detail ${id ?? 'none'}]`,
}));

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('AdminHarnessRunsPage', () => {
  it('lays out the list and the detail and passes the chosen run down', () => {
    render(<AdminHarnessRunsPage selected="r1" onSelect={vi.fn()} onClear={vi.fn()} />);
    expect(screen.getByRole('heading', { level: 1, name: 'Harness runs' })).toBeInTheDocument();
    expect(document.body).toHaveTextContent('[list r1]');
    expect(document.body).toHaveTextContent('[detail r1]');
  });

  it('on a phone the detail opens in a sheet only once a run is chosen, and closing clears it', async () => {
    vi.stubGlobal('innerWidth', 375);
    const onClear = vi.fn();
    const props = { onSelect: vi.fn(), onClear };
    const { rerender } = render(<AdminHarnessRunsPage {...props} />);
    expect(screen.queryByText('[detail r1]')).not.toBeInTheDocument();
    rerender(<AdminHarnessRunsPage selected="r1" {...props} />);
    expect(await screen.findByText('[detail r1]')).toBeInTheDocument();
    await userEvent.keyboard('{Escape}');
    expect(onClear).toHaveBeenCalled();
  });
});
