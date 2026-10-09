import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '@/shared/lib/testing';

import { ScreenSummary } from './ScreenSummary';

const state = vi.hoisted(() => ({ preview: {} }));

vi.mock('@/features/screener-builder', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useScreenerBuilder: () => ({ preview: state.preview }),
}));

const DATA = {
  session: '2026-10-02',
  decisions: { QUALIFIED: 2, WATCH: 1, REJECT: 4200 },
  coverage: { coverage: 'PARTIAL', selected: 4203, coverage_pct: 0.425, unavailable: [] },
  summary: {
    passed: 2,
    missing: 2416,
    missing_reasons: { 'no rollup.iv30@v1.iv30': 2300, 'no feature.iv_hv_spread': 116 },
    narrow_misses: [
      {
        instrument_id: 'EQ:KO',
        criterion_id: 'spread',
        field: 'f',
        value: 0.091,
        threshold: 0.1,
        distance: 0.009,
        normalised: 0.45,
      },
    ],
  },
  rows: [{ instrument_id: 'EQ:KO', symbol: 'KO' }],
};
const ready = { data: DATA, pending: false, error: null, idle: false };

beforeEach(() => {
  state.preview = ready;
});

describe('ScreenSummary', () => {
  it('shows what passed, what had no value and the decisions', async () => {
    const { container } = render(<ScreenSummary />);
    expect(screen.getByText('Session 2026-10-02')).toBeInTheDocument();
    expect(screen.getByText('4,203')).toBeInTheDocument();
    expect(screen.getByText('42.5%')).toBeInTheDocument();
    expect(screen.getByText('Qualified')).toBeInTheDocument();
    expect(screen.getByText('4,200')).toBeInTheDocument();
    expect(screen.getByText('Coverage: partial')).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it('lists the missing-data fields and the narrow misses with rule and distance', async () => {
    render(<ScreenSummary />);
    await userEvent.click(screen.getByRole('button', { name: /Missing data/ }));
    expect(screen.getByText('no rollup.iv30@v1.iv30')).toBeInTheDocument();
    expect(screen.getByText('2,300')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /Narrow misses/ }));
    expect(screen.getByText('spread (1)')).toBeInTheDocument();
    expect(screen.getByText('KO 0.091 vs 0.100, short by 0.009')).toBeInTheDocument();
  });

  it('asks for a complete criterion while idle', () => {
    state.preview = { data: undefined, pending: false, error: null, idle: true };
    render(<ScreenSummary />);
    expect(
      screen.getByText('Add a complete criterion to see the run summary.'),
    ).toBeInTheDocument();
  });

  it('shows the API error that stops the preview', () => {
    state.preview = {
      data: undefined,
      pending: false,
      error: 'my.criteria.a.field: unknown field',
      idle: false,
    };
    render(<ScreenSummary />);
    expect(screen.getByText('my.criteria.a.field: unknown field')).toBeInTheDocument();
  });

  it('shows loading until the first preview arrives', () => {
    state.preview = { data: undefined, pending: true, error: null, idle: false };
    render(<ScreenSummary />);
    expect(screen.getByText('Running the preview…')).toBeInTheDocument();
  });

  it('tells what the preview lacks, by kind, when coverage is incomplete', async () => {
    state.preview = {
      ...ready,
      data: {
        ...DATA,
        coverage: {
          ...DATA.coverage,
          unavailable: [
            {
              kind: 'SYSTEM',
              features: ['rollup.iv30@v1.iv30'],
              guide_term: 'unavailable_system',
              kind_text: 'not available because of a system error',
              cause: null,
            },
          ],
        },
      },
    };
    render(<ScreenSummary />);
    for (const line of screen.getAllByRole('button', { name: /unavailable/ }))
      await userEvent.click(line);
    expect(screen.getByText('Not available: system error')).toBeInTheDocument();
  });
});
