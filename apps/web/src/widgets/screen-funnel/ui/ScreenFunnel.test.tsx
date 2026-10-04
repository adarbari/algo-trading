import { render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '@/shared/lib/testing';

import { ScreenFunnel } from './ScreenFunnel';

const state = vi.hoisted(() => ({ preview: {} }));

vi.mock('@/features/screener-builder', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useScreenerBuilder: () => ({ preview: state.preview }),
}));

const step = (criterion_id: string, label: string | null, entering: number, remaining: number) => ({
  criterion_id,
  label,
  entering,
  remaining,
});
const DATA = {
  coverage: { selected: 4203 },
  summary: { skipped: 2416 },
  funnel: [step('iv30', 'Our 30-day IV', 4203, 486), step('close', null, 486, 45)],
};

beforeEach(() => {
  state.preview = { data: DATA, pending: false, error: null, idle: false };
});

describe('ScreenFunnel', () => {
  it('shows the universe and what remains after each gating criterion', async () => {
    const { container } = render(<ScreenFunnel />);
    const list = screen.getByRole('list', { name: 'Funnel (gating criteria)' });
    const rows = within(list).getAllByRole('listitem');
    expect(rows.map((r) => r.textContent)).toEqual([
      'Universe4,203',
      'Our 30-day IV486',
      'close45',
    ]);
    expect(screen.getByText('Skipped (missing data, never passed): 2,416')).toBeInTheDocument();
    await expectNoA11yViolations(container);
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
