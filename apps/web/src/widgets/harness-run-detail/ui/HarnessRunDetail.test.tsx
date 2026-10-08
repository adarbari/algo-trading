import { render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { lostInputFixture as lostInput, rowFixture as row } from '@/entities/harness-run';
import { expectNoA11yViolations, fakeQuery, stubElementSize } from '@/shared/lib/testing';

import { HarnessRunDetail } from './HarnessRunDetail';

const hooks = vi.hoisted(() => ({ useHarnessRunRows: vi.fn() }));
vi.mock('@/entities/harness-run', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useHarnessRunRows: hooks.useHarnessRunRows,
}));
vi.mock('@/features/guide-help', async () => {
  const { Text } = await import('@algotrade/ui');
  return { GuideHelp: ({ entry }: { entry: { id: string } }) => <Text>{`help ${entry.id}`}</Text> };
});

stubElementSize();

const rows = [row(), row({ variant: 'equal_weight', role: 'baseline', exploratory: true })];

beforeEach(() => {
  hooks.useHarnessRunRows.mockReturnValue(fakeQuery({ runId: 'run-b', rows, lostInputs: [] }));
});

describe('HarnessRunDetail', () => {
  it('asks to choose a run before one is chosen', () => {
    render(<HarnessRunDetail id={null} />);
    expect(screen.getByText('Choose a run')).toBeInTheDocument();
  });

  it("shows the run's rows with the rates and the exploratory label", async () => {
    const { container } = render(<HarnessRunDetail id="run-b" />);
    const table = screen.getByRole('grid', { name: 'Run rows' });
    const screener = within(table).getByRole('row', { name: /momentum_12_1 \(screener\)/ });
    expect(within(screener).getByText('58.0%')).toBeInTheDocument();
    expect(within(screener).getByText('frozen 2024-01-01')).toBeInTheDocument();
    const baseline = within(table).getByRole('row', { name: /equal_weight \(baseline\)/ });
    expect(within(baseline).getByText('EXPLORATORY')).toBeInTheDocument();
    expect(screen.getByText('help hit_rate')).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it('lists the input tables a variant lacked, with the sessions lost to each', () => {
    hooks.useHarnessRunRows.mockReturnValue(
      fakeQuery({ runId: 'run-b', rows, lostInputs: [lostInput()] }),
    );
    render(<HarnessRunDetail id="run-b" />);
    const table = screen.getByRole('grid', { name: 'Missing input tables' });
    const lost = within(table).getByRole('row', { name: /main\/momentum_12_1/ });
    expect(within(lost).getByText('rollups/instrument/ibkr_iv@v1')).toBeInTheDocument();
    expect(within(lost).getByText('4')).toBeInTheDocument();
  });

  it('shows no missing-tables table when none were lost', () => {
    render(<HarnessRunDetail id="run-b" />);
    expect(screen.queryByRole('grid', { name: 'Missing input tables' })).not.toBeInTheDocument();
  });

  it('shows the loading, error and empty states', () => {
    hooks.useHarnessRunRows.mockReturnValue(fakeQuery(undefined));
    const { rerender } = render(<HarnessRunDetail id="run-b" />);
    expect(screen.getByText('Loading run rows…')).toBeInTheDocument();
    hooks.useHarnessRunRows.mockReturnValue(fakeQuery(undefined, { isError: true }));
    rerender(<HarnessRunDetail id="run-b" />);
    expect(screen.getByText("The run's rows failed to load.")).toBeInTheDocument();
    hooks.useHarnessRunRows.mockReturnValue(
      fakeQuery({ runId: 'run-b', rows: [], lostInputs: [] }),
    );
    rerender(<HarnessRunDetail id="run-b" />);
    expect(screen.getByText('The run holds no rows.')).toBeInTheDocument();
  });
});
