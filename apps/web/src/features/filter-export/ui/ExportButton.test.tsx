import { Text } from '@algotrade/ui';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ExportButton } from './ExportButton';

const hooks = vi.hoisted(() => ({ useSurfaceExport: vi.fn(), mutate: vi.fn() }));

vi.mock('../api/use-surface-export', () => ({ useSurfaceExport: hooks.useSurfaceExport }));

beforeEach(() => {
  hooks.mutate.mockReset();
  hooks.useSurfaceExport.mockReturnValue({
    mutate: hooks.mutate,
    isPending: false,
    isError: false,
  });
});

describe('ExportButton', () => {
  it('saves the surface under the filters in force, shows its help and says when the file failed', async () => {
    const { rerender } = render(
      <ExportButton
        surface="ideas"
        f="decision:QUALIFIED"
        session="2026-10-01"
        help={<Text>help</Text>}
      />,
    );
    expect(hooks.useSurfaceExport).toHaveBeenCalledWith('ideas');
    expect(screen.getByText('help')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Export' }));
    expect(hooks.mutate).toHaveBeenCalledWith({
      f: 'decision:QUALIFIED',
      session: '2026-10-01',
      screener: undefined,
      columns: undefined,
    });
    hooks.useSurfaceExport.mockReturnValue({
      mutate: hooks.mutate,
      isPending: false,
      isError: true,
    });
    rerender(
      <ExportButton surface="screener_results" f="" screener="vrp" columns={['feature.close']} />,
    );
    await userEvent.click(screen.getByRole('button', { name: 'Export' }));
    expect(hooks.mutate).toHaveBeenLastCalledWith({
      f: '',
      session: undefined,
      screener: 'vrp',
      columns: ['feature.close'],
    });
    expect(screen.getByText('The file could not be saved.')).toBeInTheDocument();
  });
});
