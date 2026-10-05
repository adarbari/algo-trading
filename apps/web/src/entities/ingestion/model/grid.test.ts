import { describe, expect, it } from 'vitest';

import { cellShare, defaultCell, findCell, gridColumns, gridRows, shareText } from './grid';
import { completenessSummary, staleSince } from './summary';
import type { Completeness, CompletenessCell } from './types';

const cell = (
  dataset: string,
  session: string,
  status: string,
  present: number,
  expected: number | null,
): CompletenessCell => ({ dataset, session, status, present, expected, basis: '', runIds: [] });

// Shaped like the real grid of 2026-10-02: chains start on the last session, bars complete.
const grid: Completeness = {
  sessions: ['2026-09-30', '2026-10-01', '2026-10-02'],
  datasets: ['bars/1d', 'chains/option_quotes', 'universe'],
  lastClosed: '2026-10-02',
  cells: [
    cell('bars/1d', '2026-09-30', 'COMPLETE', 12590, 12580),
    cell('bars/1d', '2026-10-01', 'COMPLETE', 12594, 12590),
    cell('bars/1d', '2026-10-02', 'COMPLETE', 12601, 12594),
    cell('chains/option_quotes', '2026-09-30', 'MISSING', 0, null),
    cell('chains/option_quotes', '2026-10-01', 'MISSING', 0, null),
    cell('chains/option_quotes', '2026-10-02', 'PARTIAL', 3623, 4203),
    cell('universe', '2026-09-30', 'COMPLETE', 11427, null),
    cell('universe', '2026-10-01', 'CARRIED', 11427, null),
    cell('universe', '2026-10-02', 'MISSING', 0, null),
  ],
};

describe('completeness grid', () => {
  it('shows the share of expected rows', () => {
    expect(shareText(cellShare(cell('x', 'd', 'PARTIAL', 3623, 4203)))).toBe('86.2');
    expect(shareText(cellShare(cell('x', 'd', 'COMPLETE', 12601, 12594)))).toBe('100');
    expect(shareText(cellShare(cell('x', 'd', 'COMPLETE', 1, null)))).toBe('');
  });

  it('maps statuses: not collected before the first data, failed after', () => {
    const rows = gridRows(grid);
    expect(rows.map((r) => r.label)).toEqual(['Daily bars', 'Option chains', 'Universe']);
    const [, chains, universe] = rows;
    expect(chains?.cells['2026-09-30']?.status).toBe('not-collected');
    expect(chains?.cells['2026-10-02']).toEqual({ status: 'partial', text: '86.2' });
    expect(universe?.cells['2026-10-01']?.status).toBe('complete');
    expect(universe?.cells['2026-10-02']?.status).toBe('failed');
    expect(chains?.cells['2026-10-01']?.text).toBe('');
    expect(gridColumns(grid).map((c) => c.label)).toEqual(['30 Sept', '1 Oct', 'Fri 2']);
  });

  it('drills into the worst cell of the latest session first', () => {
    expect(defaultCell(grid)).toEqual({ dataset: 'universe', session: '2026-10-02' });
    expect(defaultCell({ ...grid, sessions: [] })).toBeNull();
    expect(findCell(grid, { dataset: 'bars/1d', session: '2026-10-01' })?.present).toBe(12594);
  });

  it('summarises the latest session', () => {
    const summary = completenessSummary(grid);
    expect(summary).toMatchObject({ session: '2026-10-02', datasets: 3, complete: 1 });
    expect(summary).toMatchObject({ partial: 1, failed: 1, notCollected: 0 });
    expect(summary?.share).toBeCloseTo((12594 + 3623) / (12594 + 4203));
    expect(completenessSummary({ ...grid, sessions: [] })).toBeNull();
  });

  it('is stale when the exchange closed a later session', () => {
    expect(staleSince(grid)).toBeNull();
    expect(staleSince({ ...grid, lastClosed: '2026-10-05' })).toBe('2026-10-02');
  });
});
