import { render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { recordFixture as record } from '@/entities/screener-run';
import { expectNoA11yViolations, fakeQuery, stubElementSize } from '@/shared/lib/testing';

import { ScreenerRunDetail } from './ScreenerRunDetail';

const hooks = vi.hoisted(() => ({ useScreenerRun: vi.fn() }));
vi.mock('@/entities/screener-run', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useScreenerRun: hooks.useScreenerRun,
}));
vi.mock('@/features/guide-help', async () => {
  const { Text } = await import('@algotrade/ui');
  return {
    GuideHelp: ({ entry }: { entry: { id: string } }) => <Text>{`help ${entry.id}`}</Text>,
    termHelp: (id: string) => <Text>{`help ${id}`}</Text>,
    Labelled: ({ text, help }: { text: string; help: string }) => (
      <Text>{`${text} help ${help}`}</Text>
    ),
  };
});

stubElementSize();

beforeEach(() => {
  hooks.useScreenerRun.mockReturnValue(fakeQuery(record()));
});

describe('ScreenerRunDetail', () => {
  it('asks to choose a run before one is chosen', () => {
    render(<ScreenerRunDetail id={null} />);
    expect(screen.getByText('Choose a run')).toBeInTheDocument();
  });

  it('shows the run, its decisions, its changes and the link to the screener', async () => {
    const { container } = render(<ScreenerRunDetail id="screen-trend-site-1" />);
    const facts = screen.getByLabelText('Run');
    expect(within(facts).getByText('version 3, hash a1b2c3d4')).toBeInTheDocument();
    expect(within(facts).getByText('rollups/instrument/ibkr_iv@v1')).toBeInTheDocument();
    expect(within(screen.getByLabelText('Decisions')).getByText('qualified')).toBeInTheDocument();
    const changes = screen.getByLabelText('Changes');
    expect(within(changes).getByText(/screen-trend-site-0/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: "Open the screener's results" })).toHaveAttribute(
      'href',
      '/screeners/trend_pullback',
    );
    await expectNoA11yViolations(container);
  });

  it('says not recorded for what the run never wrote, never zero', () => {
    hooks.useScreenerRun.mockReturnValue(
      fakeQuery(
        record({
          status: 'FAILED',
          picked: null,
          paused: null,
          regime: null,
          coverage: null,
          configVersion: null,
          configHash: null,
          decisions: null,
          changes: null,
        }),
      ),
    );
    render(<ScreenerRunDetail id="screen-trend-site-1" />);
    expect(screen.getAllByText('Not recorded').length).toBeGreaterThanOrEqual(6);
    expect(screen.queryByText('0')).not.toBeInTheDocument();
  });

  it('shows the loading, error and missing states', () => {
    hooks.useScreenerRun.mockReturnValue(fakeQuery(undefined));
    const { rerender } = render(<ScreenerRunDetail id="r" />);
    expect(screen.getByText('Loading the run…')).toBeInTheDocument();
    hooks.useScreenerRun.mockReturnValue(fakeQuery(undefined, { isError: true }));
    rerender(<ScreenerRunDetail id="r" />);
    expect(screen.getByText('The run failed to load.')).toBeInTheDocument();
    hooks.useScreenerRun.mockReturnValue(fakeQuery(null));
    rerender(<ScreenerRunDetail id="r" />);
    expect(screen.getByText('No such run is recorded.')).toBeInTheDocument();
  });
});
