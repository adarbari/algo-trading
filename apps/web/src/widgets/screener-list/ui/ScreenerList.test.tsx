import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ScreenerSummary } from '@/entities/screen';
import { TestQueryProvider } from '@/shared/api';
import { expectNoA11yViolations, fakeQuery, stubElementSize } from '@/shared/lib/testing';

import { ScreenerList } from './ScreenerList';

const hooks = vi.hoisted(() => ({ useScreeners: vi.fn() }));
vi.mock('@/entities/screen', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useScreeners: hooks.useScreeners,
}));
vi.mock('@/features/screener-copy', async () => {
  const { Button } = await import('@algotrade/ui');
  return {
    CopyPresetDialog: ({
      preset,
      onCopied,
    }: {
      preset: string;
      onCopied: (id: string) => void;
    }) => (
      <Button
        onClick={() => {
          onCopied(`my-${preset}`);
        }}
      >
        {`finish copy of ${preset}`}
      </Button>
    ),
  };
});

stubElementSize();

const screener = (
  config_id: string,
  scope: string,
  impl: string,
  patch: Partial<ScreenerSummary> = {},
): ScreenerSummary => ({
  config_id,
  scope,
  kind: 'screener',
  impl,
  schedule: null,
  selection: 'liquid_optionable',
  hash: 'h',
  error: null,
  ...patch,
});
const LIST = [
  screener('vrp_scanner', 'site', 'rules'),
  screener('short_premium', 'site', 'short_premium_liquidity'),
  screener('my-vrp', 'abhinav', 'rules', { schedule: 'nightly' }),
  screener('broken', 'abhinav', 'rules', { error: 'unknown field' }),
];

beforeEach(() => {
  hooks.useScreeners.mockReturnValue(fakeQuery(LIST));
});

const setup = () => {
  const onOpen = vi.fn();
  const view = render(
    <TestQueryProvider>
      <ScreenerList onOpen={onOpen} />
    </TestQueryProvider>,
  );
  return { onOpen, ...view };
};

describe('ScreenerList', () => {
  it('separates your screeners from the site presets', async () => {
    const { container } = setup();
    const mine = screen.getByRole('grid', { name: 'Your screeners' });
    expect(within(mine).getByRole('row', { name: /my-vrp/ })).toHaveTextContent('Nightly');
    expect(within(mine).getByRole('row', { name: /broken/ })).toHaveTextContent('Does not resolve');
    const presets = screen.getByRole('grid', { name: 'Site presets' });
    expect(within(presets).getByRole('row', { name: /short_premium/ })).toHaveTextContent('Python');
    expect(
      within(presets)
        .getByRole('row', { name: /short_premium/ })
        .querySelector('button'),
    ).toBeNull();
    await expectNoA11yViolations(container);
  });

  it('opens a screener to edit, and a preset to view', async () => {
    const { onOpen } = setup();
    await userEvent.click(
      within(screen.getByRole('row', { name: /my-vrp/ })).getByRole('button', { name: 'Edit' }),
    );
    expect(onOpen).toHaveBeenCalledWith('my-vrp');
    await userEvent.click(
      within(screen.getByRole('row', { name: /vrp_scanner/ })).getByRole('button', {
        name: 'View',
      }),
    );
    expect(onOpen).toHaveBeenLastCalledWith('vrp_scanner');
  });

  it('copies a preset and opens the copy', async () => {
    const { onOpen } = setup();
    await userEvent.click(
      within(screen.getByRole('row', { name: /vrp_scanner/ })).getByRole('button', {
        name: 'Copy to my screeners',
      }),
    );
    await userEvent.click(screen.getByRole('button', { name: 'finish copy of vrp_scanner' }));
    expect(onOpen).toHaveBeenCalledWith('my-vrp_scanner');
    expect(screen.queryByRole('button', { name: /finish copy/ })).toBeNull();
  });

  it('says when you have none yet, and when the list failed to load', () => {
    hooks.useScreeners.mockReturnValue(fakeQuery([LIST[0]]));
    const { rerender } = setup();
    expect(
      screen.getByText('You have no finalized screener yet. Create one, or copy a preset.'),
    ).toBeInTheDocument();
    hooks.useScreeners.mockReturnValue(fakeQuery(undefined, { isError: true, isPending: false }));
    rerender(
      <TestQueryProvider>
        <ScreenerList onOpen={vi.fn()} />
      </TestQueryProvider>,
    );
    expect(screen.getAllByText('The screeners failed to load.').length).toBeGreaterThan(0);
  });
});
