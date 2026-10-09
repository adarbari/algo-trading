import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { RUNS_FIXTURE } from '@/entities/harness-run';
import { expectNoA11yViolations, fakeQuery, stubElementSize } from '@/shared/lib/testing';

import { HarnessRunList } from './HarnessRunList';

const hooks = vi.hoisted(() => ({ useHarnessRuns: vi.fn() }));
vi.mock('@/entities/harness-run', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useHarnessRuns: hooks.useHarnessRuns,
}));
vi.mock('@/features/guide-help', async () => {
  const { Text } = await import('@algotrade/ui');
  return { GuideHelp: ({ entry }: { entry: { id: string } }) => <Text>{`help ${entry.id}`}</Text> };
});

stubElementSize();

beforeEach(() => {
  hooks.useHarnessRuns.mockReturnValue(fakeQuery(RUNS_FIXTURE));
});

describe('HarnessRunList', () => {
  it('lists each run with its split, exclusions and Guide buttons; unrecorded figures stay empty', async () => {
    const { container } = render(<HarnessRunList selected={null} onSelect={vi.fn()} />);
    const table = screen.getByRole('grid', { name: 'Harness runs' });
    const done = within(table).getByRole('row', { name: /run-b/ });
    expect(within(done).getByText('complete')).toBeInTheDocument();
    expect(within(done).getByText('2024-01-01')).toBeInTheDocument();
    expect(within(done).getByText('2012-01-03 to 2026-10-02')).toBeInTheDocument();
    expect(within(done).getByText('92%')).toBeInTheDocument();
    const failed = within(table).getByRole('row', { name: /run-a/ });
    expect(within(failed).getByText('failed')).toBeInTheDocument();
    expect(within(failed).getByText('EXPLORATORY')).toBeInTheDocument();
    expect(within(failed).queryByText('0')).not.toBeInTheDocument();
    expect(screen.getAllByText('help harness_exclusions').length).toBeGreaterThan(0);
    expect(screen.getByText('help variants_tried')).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it('selects a run on a row click', async () => {
    const onSelect = vi.fn();
    render(<HarnessRunList selected={null} onSelect={onSelect} />);
    await userEvent.click(screen.getByRole('row', { name: /run-b/ }));
    expect(onSelect).toHaveBeenCalledWith('run-b');
  });

  it('shows the loading, error and empty states', () => {
    hooks.useHarnessRuns.mockReturnValue(fakeQuery(undefined));
    const { rerender } = render(<HarnessRunList selected={null} onSelect={vi.fn()} />);
    expect(screen.getByText('Loading harness runs…')).toBeInTheDocument();
    hooks.useHarnessRuns.mockReturnValue(fakeQuery(undefined, { isError: true }));
    rerender(<HarnessRunList selected={null} onSelect={vi.fn()} />);
    expect(screen.getByText('The harness runs failed to load.')).toBeInTheDocument();
    hooks.useHarnessRuns.mockReturnValue(fakeQuery([]));
    rerender(<HarnessRunList selected={null} onSelect={vi.fn()} />);
    expect(screen.getByText('No evaluation run is recorded.')).toBeInTheDocument();
  });
});
