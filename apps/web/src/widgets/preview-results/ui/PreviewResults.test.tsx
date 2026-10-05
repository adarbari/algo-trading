import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations, stubElementSize } from '@/shared/lib/testing';

import { PreviewResults } from './PreviewResults';

const state = vi.hoisted(() => ({ preview: {} }));

vi.mock('@/features/screener-builder', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useScreenerBuilder: () => ({ preview: state.preview }),
}));

vi.mock('@/entities/feature', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useFeatureCatalogue: () => ({ data: CATALOGUE }),
}));

const feature = (name: string, unit: string, description: string) => ({
  name,
  dtype: 'float64',
  unit,
  description,
  kind: 'expression',
  scope: 'site',
});
const CATALOGUE = [
  feature('feature.vrp_iv30', 'decimal', 'Lower of IBKR and Cboe IV30'),
  feature('feature.vrp_iv_hv_ratio', 'ratio', 'IV30 / HV30'),
  feature('feature.pct_from_high_52w', 'decimal', 'Distance from the 52-week high'),
];

const criterion = (id: string, field: string, value: number, outcome = 'PASS') => ({
  criterion_id: id,
  field,
  mode: 'hard',
  value,
  outcome,
  distance: null,
  normalised: null,
  penalty: 0,
});

const row = (
  rank: number,
  symbol: string,
  decision: string,
  score: number,
  columns: Record<string, unknown> = {},
) => ({
  instrument_id: `EQ:${symbol}`,
  symbol,
  rank,
  decision,
  score,
  columns,
  criteria: [
    criterion('security_type', 'instrument.security_type', 0),
    criterion('iv30', 'feature.vrp_iv30', 0.61),
    criterion(
      'iv_hv_ratio',
      'feature.vrp_iv_hv_ratio',
      rank === 3 ? 1.08 : 1.22,
      rank === 3 ? 'NEAR' : 'PASS',
    ),
  ],
  flags: rank === 1 ? ['leveraged'] : [],
  reasons: decision === 'WATCH' ? ['spread within tolerance'] : [],
});
const DATA = {
  session: '2026-10-02',
  total: 4203,
  decisions: { QUALIFIED: 2, WATCH: 1, REJECT: 100 },
  rows: [
    row(1, 'AAPL', 'QUALIFIED', 92, { next_earnings: '2026-10-29', pct_from_high_52w: -0.5 }),
    row(2, 'MSFT', 'QUALIFIED', 88),
    row(3, 'KO', 'WATCH', 79),
  ],
};

stubElementSize();

beforeEach(() => {
  state.preview = { data: DATA, pending: false, error: null, idle: false };
});

describe('PreviewResults', () => {
  it('lists the top rows with decision counts in the title and the screen columns', async () => {
    const { container } = render(<PreviewResults onOpen={vi.fn()} />);
    expect(
      screen.getByRole('heading', { name: 'Preview · 2 qualified · 1 watch' }),
    ).toBeInTheDocument();
    expect(screen.getByText('Top 3 of 4,203 on 2026-10-02')).toBeInTheDocument();
    const grid = screen.getByRole('grid', { name: 'Preview results' });
    expect(grid).toHaveTextContent('Next earnings');
    expect(screen.getByRole('row', { name: /AAPL/ })).toHaveTextContent('leveraged');
    expect(screen.getByRole('row', { name: /KO/ })).toHaveTextContent('spread within tolerance');
    await expectNoA11yViolations(container);
  });

  it('shows each criterion and display column in its unit, tinting a near miss', () => {
    const { container } = render(<PreviewResults onOpen={vi.fn()} />);
    const grid = screen.getByRole('grid', { name: 'Preview results' });
    for (const header of ['IV30', 'IV/HV', 'From high']) expect(grid).toHaveTextContent(header);
    expect(within(grid).queryByText(/security type/i)).toBeNull(); // a gate: no column
    expect(screen.getByRole('row', { name: /AAPL/ })).toHaveTextContent('61.0%');
    expect(screen.getByRole('row', { name: /AAPL/ })).toHaveTextContent('−50.0%'); // From high
    const tinted = [...container.querySelectorAll('[data-fill]')];
    expect(tinted.map((c) => [c.getAttribute('data-fill'), c.textContent])).toEqual([
      ['warning', '1.08'],
    ]);
  });

  it('filters by decision and opens a ticker', async () => {
    const onOpen = vi.fn();
    render(<PreviewResults onOpen={onOpen} />);
    await userEvent.click(screen.getByRole('button', { name: 'Watch' }));
    expect(screen.queryByRole('row', { name: /AAPL/ })).toBeNull();
    await userEvent.click(screen.getByText('KO'));
    expect(onOpen).toHaveBeenCalledWith('KO');
  });

  it('asks for a complete criterion while idle', () => {
    state.preview = { data: undefined, pending: false, error: null, idle: true };
    render(<PreviewResults onOpen={vi.fn()} />);
    expect(
      screen.getByText('Add a complete criterion to preview what it would pick.'),
    ).toBeInTheDocument();
  });
});
