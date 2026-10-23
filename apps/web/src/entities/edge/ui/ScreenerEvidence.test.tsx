import { Text } from '@algotrade/ui';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { TestQueryProvider } from '@/shared/api';
import { expectNoA11yViolations, fakeQuery } from '@/shared/lib/testing';

import { TRACK_RECORDS_FIXTURE } from '../model/fixtures';
import { toTrackRecords, type TrackEntry } from '../model/track-records';
import { EDGES_SHOWN, ScreenerEvidenceCell, ScreenerEvidenceDetail } from './ScreenerEvidence';

const hooks = vi.hoisted(() => ({ useTrackRecords: vi.fn() }));
vi.mock('../api/track-records', () => ({ useTrackRecords: hooks.useTrackRecords }));

const records = toTrackRecords(TRACK_RECORDS_FIXTURE);
const serve = (id: string) => {
  hooks.useTrackRecords.mockReturnValue(fakeQuery(records.get(id) ?? []));
};

const cell = (open = false, onOpenChange = vi.fn()) =>
  render(
    <TestQueryProvider>
      <ScreenerEvidenceCell screenerId="s" open={open} onOpenChange={onOpenChange} />
    </TestQueryProvider>,
  );

describe('ScreenerEvidenceCell', () => {
  it('shows the strongest edge: win vs base, lift, trades, hold, edge, more edges, status', async () => {
    serve('momentum_12_1');
    const onOpenChange = vi.fn();
    const { container } = cell(false, onOpenChange);
    const headline = screen.getByRole('button', { name: 'Win 58% vs 51% base' });
    expect(headline).toHaveAttribute('aria-expanded', 'false');
    expect(screen.getByText('+7 pts')).toBeInTheDocument();
    expect(screen.getByText('80 trades · 21-session hold')).toBeInTheDocument();
    expect(screen.getByText('Earnings drift')).toBeInTheDocument();
    expect(screen.getByText('+1 edge')).toBeInTheDocument();
    expect(screen.getByText('Evidenced')).toBeInTheDocument();
    await userEvent.click(headline);
    expect(onOpenChange).toHaveBeenCalledWith(true);
    await expectNoA11yViolations(container);
  });

  it('says "No record yet" with the server words when the edge has no frozen run', () => {
    serve('vrp_scanner');
    cell();
    expect(screen.getByText('No record yet')).toBeInTheDocument();
    expect(screen.getByText('not run yet')).toBeInTheDocument();
    expect(screen.getByText('VRP')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'No record yet' })).toBeNull();
    expect(screen.queryByText(/%/)).toBeNull();
  });

  it('says how few trades there are under 20 since the freeze, never the bare rate', () => {
    const [e] = records.get('momentum_12_1') as TrackEntry[];
    const few = { ...e, horizons: [{ ...e?.horizons[0], sessions: 12 }] } as TrackEntry;
    hooks.useTrackRecords.mockReturnValue(fakeQuery([few]));
    cell();
    expect(screen.getByText('No record yet')).toBeInTheDocument();
    expect(screen.getByText(/Only 12 trades since the freeze; 20 are needed/)).toBeInTheDocument();
    expect(screen.queryByText(/58%/)).toBeNull();
  });

  it('says a partial run is partial', () => {
    const [e] = records.get('momentum_12_1') as TrackEntry[];
    const partial = { ...e, horizons: [{ ...e?.horizons[0], baseRate: null }] } as TrackEntry;
    hooks.useTrackRecords.mockReturnValue(fakeQuery([partial]));
    cell();
    expect(screen.getByText(/The run is partial/)).toBeInTheDocument();
  });

  it('says a screener in no edge is not part of one, with nothing to open', () => {
    serve('plain');
    cell();
    expect(screen.getByText('Not part of an edge')).toBeInTheDocument();
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('says when the evidence failed to load', () => {
    hooks.useTrackRecords.mockReturnValue(fakeQuery(undefined, { isError: true }));
    cell();
    expect(screen.getByText('The evidence failed to load')).toBeInTheDocument();
  });
});

describe('ScreenerEvidenceDetail', () => {
  const detail = (onOpenEdge = vi.fn()) =>
    render(
      <TestQueryProvider>
        <ScreenerEvidenceDetail screenerId="s" onOpenEdge={onOpenEdge} help={<Text>help</Text>} />
      </TestQueryProvider>,
    );

  it('lists one block per edge with its figures, freeze date and an Open edge button', async () => {
    serve('momentum_12_1');
    const onOpenEdge = vi.fn();
    const { container } = detail(onOpenEdge);
    const list = screen.getByRole('list', { name: 'Edges of s' });
    expect(list.querySelectorAll('li')).toHaveLength(2);
    expect(screen.getByText('How to read a record')).toBeInTheDocument();
    expect(
      screen.getByText(/80 trades · 21-session hold · Frozen since 1 May 2026/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/120 trades · 21-session hold · Frozen since 1 Apr 2026/),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Open edge Momentum 12-1' }));
    expect(onOpenEdge).toHaveBeenCalledWith('momentum_12_1');
    await expectNoA11yViolations(container);
  });

  it('caps at three edges and shows the rest on "Show all"', async () => {
    const [base] = records.get('momentum_12_1') as TrackEntry[];
    const many = Array.from({ length: 5 }, (_, i) => ({
      ...base,
      edgeId: `edge_${String(i)}`,
      edgeName: `Edge ${String(i)}`,
    })) as TrackEntry[];
    hooks.useTrackRecords.mockReturnValue(fakeQuery(many));
    detail();
    expect(screen.getAllByRole('listitem')).toHaveLength(EDGES_SHOWN);
    expect(screen.getByText('+2 more edges')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Show all' }));
    expect(screen.getAllByRole('listitem')).toHaveLength(5);
    expect(screen.queryByText(/more edges/)).toBeNull();
  });

  it('gives the reason of an edge with no record in its block', () => {
    serve('vrp_scanner');
    detail();
    expect(screen.getByText(/No record yet: not run yet/)).toBeInTheDocument();
  });
});
