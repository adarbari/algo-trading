import { render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '@/shared/lib/testing';

import { ScreenFunnel } from './ScreenFunnel';

const state = vi.hoisted(() => ({ preview: {}, criteria: [] as unknown[] }));

vi.mock('@/features/screener-builder', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useScreenerBuilder: () => ({ preview: state.preview, criteria: state.criteria }),
}));
vi.mock('@/entities/feature', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useFeatureCatalogue: () => ({
    data: [{ name: 'feature.vrp_iv30', dtype: 'float32', unit: 'decimal', categories: [] }],
  }),
}));

const step = (criterion_id: string, entering: number, remaining: number) => ({
  criterion_id,
  entering,
  remaining,
});
const DATA = {
  coverage: { selected: 4203 },
  summary: { skipped: 2416 },
  funnel: [step('iv30', 4203, 486), step('close', 486, 45)],
};

beforeEach(() => {
  state.preview = { data: DATA, pending: false, error: null, idle: false };
  state.criteria = [];
});

describe('ScreenFunnel', () => {
  it('shows the universe and what remains after each gating criterion', async () => {
    const { container } = render(<ScreenFunnel />);
    const list = screen.getByRole('list', { name: 'Funnel (gating criteria)' });
    const rows = within(list).getAllByRole('listitem');
    expect(rows.map((r) => r.textContent)).toEqual(['Universe4,203', 'iv30486', 'close45']);
    expect(screen.getByText('Skipped (missing data, never passed): 2,416')).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it('names a step from the criterion as edited, not from its stored label', () => {
    state.criteria = [
      { id: 'iv30', field: 'feature.vrp_iv30', op: 'gt', value: 1.5, mode: 'hard' },
    ];
    render(<ScreenFunnel />);
    const rows = within(
      screen.getByRole('list', { name: 'Funnel (gating criteria)' }),
    ).getAllByRole('listitem');
    expect(rows[1]?.textContent).toBe('IV30 > 150%486');
    expect(rows[2]?.textContent).toBe('close45');
  });

  it('says when there is no gating criterion', () => {
    state.preview = { data: { ...DATA, funnel: [] }, pending: false, error: null, idle: false };
    render(<ScreenFunnel />);
    expect(
      screen.getByText('No hard or soft criterion: every row is screened.'),
    ).toBeInTheDocument();
  });

  it('is empty while idle and shows the API error', () => {
    state.preview = { data: undefined, pending: false, error: null, idle: true };
    const { rerender } = render(<ScreenFunnel />);
    expect(screen.getByText('Add a complete criterion to see the funnel.')).toBeInTheDocument();
    state.preview = { data: undefined, pending: false, error: 'bad spec', idle: false };
    rerender(<ScreenFunnel />);
    expect(screen.getByText('bad spec')).toBeInTheDocument();
  });
});
