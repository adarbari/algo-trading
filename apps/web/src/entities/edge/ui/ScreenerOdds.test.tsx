import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { fakeQuery } from '@/shared/lib/testing';

import { TRACK_RECORDS_FIXTURE } from '../model/fixtures';
import { toTrackRecords } from '../model/track-records';
import { ScreenerOdds } from './ScreenerOdds';
import { ScreenerTrackChip } from './ScreenerTrackChip';

const hook = vi.hoisted(() => ({ useTrackRecords: vi.fn() }));
vi.mock('../api/track-records', () => ({ useTrackRecords: hook.useTrackRecords }));

const records = toTrackRecords(TRACK_RECORDS_FIXTURE);
const answer = (id: string) =>
  hook.useTrackRecords.mockReturnValue(fakeQuery(records.get(id) ?? []));

beforeEach(() => {
  hook.useTrackRecords.mockReset();
});

describe('ScreenerOdds', () => {
  it('shows the first run that ran: hit rate against base rate, lift, sessions and the run', () => {
    answer('momentum_12_1');
    render(<ScreenerOdds screenerId="momentum_12_1" />);
    expect(screen.getByText('58.0%')).toBeInTheDocument();
    expect(screen.getByText('vs 51.0% base')).toBeInTheDocument();
    expect(screen.getByText('120')).toBeInTheDocument();
    expect(screen.getByText(/momentum_12_1 from 2024-01-01/)).toBeInTheDocument();
    expect(screen.queryByText('EXPLORATORY')).not.toBeInTheDocument();
  });

  it('says why when no edge ran, and shows nothing when no edge lists the screener', () => {
    answer('vrp_scanner');
    const { container, rerender } = render(<ScreenerOdds screenerId="vrp_scanner" />);
    expect(screen.getByText('not run yet')).toBeInTheDocument();
    answer('plain');
    rerender(<ScreenerOdds screenerId="plain" />);
    expect(container).toBeEmptyDOMElement();
  });

  it('shows a loading and an error state', () => {
    hook.useTrackRecords.mockReturnValue(fakeQuery(undefined, { isPending: true }));
    const { rerender } = render(<ScreenerOdds screenerId="x" />);
    expect(screen.getByText('Loading odds…')).toBeInTheDocument();
    hook.useTrackRecords.mockReturnValue(fakeQuery(undefined, { isError: true }));
    rerender(<ScreenerOdds screenerId="x" />);
    expect(screen.getByRole('alert')).toHaveTextContent('Odds failed to load');
  });
});

describe('ScreenerTrackChip', () => {
  it('shows the first edge as a candidate with its sessions and the others as a count', () => {
    answer('momentum_12_1');
    render(<ScreenerTrackChip screenerId="momentum_12_1" />);
    expect(screen.getByText('Candidate · 120 sessions')).toBeInTheDocument();
    expect(screen.getByText('+1')).toBeInTheDocument();
  });

  it('says Not run for an edge without a run and nothing for an unlisted screener', () => {
    answer('vrp_scanner');
    const { container, rerender } = render(<ScreenerTrackChip screenerId="vrp_scanner" />);
    expect(screen.getByText('Not run')).toBeInTheDocument();
    answer('plain');
    rerender(<ScreenerTrackChip screenerId="plain" />);
    expect(container).toBeEmptyDOMElement();
  });
});
