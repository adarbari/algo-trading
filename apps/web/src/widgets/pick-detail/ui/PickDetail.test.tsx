import { Stack, Text } from '@algotrade/ui';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type { CriterionInfo, TableRow } from '@/entities/feature';
import { expectNoA11yViolations } from '@/shared/lib/testing';

import { PickDetail } from './PickDetail';

// The scorecard (entities/screen) reads the catalogue and the screen; its own test covers that.
vi.mock('@/entities/screen', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  CriteriaScorecard: (props: {
    screenerId: string;
    entries: readonly { id: string; outcome: string }[];
  }) => (
    <Stack aria-label={`Criteria of ${props.screenerId}`}>
      {props.entries.map((e) => (
        <Text key={e.id}>{`${e.id} ${e.outcome}`}</Text>
      ))}
    </Stack>
  ),
}));

const CRITERIA: CriterionInfo[] = [
  { id: 'optionable', field: 'instrument.optionable', mode: 'hard' },
  { id: 'iv30', field: 'rollup.iv30@v1.iv30', mode: 'hard' },
  { id: 'ratio', field: 'feature.iv_hv_ratio', mode: 'soft' },
];
const ROW: TableRow = {
  rank: 2,
  instrumentId: 'EQ:SOXS',
  symbol: 'SOXS',
  name: 'Direxion Semiconductor Bear 3X',
  decision: 'QUALIFIED',
  score: 90,
  reasons: 'ratio 1.08 below 1.25 (within tolerance)',
  flags: ['leveraged_inverse'],
  change: 'new',
  previousDecision: null,
  criteria: {
    optionable: { value: 1, outcome: 'PASS' },
    iv30: { value: 1.11, outcome: 'PASS' },
    ratio: { value: 1.08, outcome: 'NEAR' },
  },
  columns: {},
  cells: {},
};

function setup(overrides: Partial<Parameters<typeof PickDetail>[0]> = {}) {
  const handlers = { onOpen: vi.fn(), onToggleCompare: vi.fn(), onDismiss: vi.fn() };
  const view = render(
    <PickDetail
      row={ROW}
      screenerId="vrp"
      criteria={CRITERIA}
      compared={false}
      {...handlers}
      {...overrides}
    />,
  );
  return { ...handlers, ...view };
}

describe('PickDetail', () => {
  it('shows the pick, why, each criterion in its unit with its outcome (not the gates)', async () => {
    const { container } = setup();
    expect(screen.getByRole('heading', { name: 'SOXS' })).toBeInTheDocument();
    expect(screen.getByText('Score 90 · new since the previous run')).toBeInTheDocument();
    expect(screen.getByText('Flags: leveraged_inverse')).toBeInTheDocument();
    // The reasons text is the server's raw wording: only a paused pick shows it.
    expect(screen.queryByText('ratio 1.08 below 1.25 (within tolerance)')).toBeNull();
    const criteria = screen.getByLabelText('Criteria of vrp');
    expect(criteria).toHaveTextContent('iv30 PASS');
    expect(criteria).toHaveTextContent('ratio NEAR');
    await expectNoA11yViolations(container);
  });

  it('opens the ticker, toggles the compare set and dismisses', async () => {
    const { onOpen, onToggleCompare, onDismiss } = setup();
    await userEvent.click(screen.getByRole('button', { name: 'Open in Explore' }));
    expect(onOpen).toHaveBeenCalledWith('SOXS');
    await userEvent.click(screen.getByRole('button', { name: 'Add to compare' }));
    expect(onToggleCompare).toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', { name: 'Dismiss' }));
    expect(onDismiss).toHaveBeenCalled();
  });

  it('says what a dropped pick was', () => {
    setup({ row: { ...ROW, change: 'dropped', previousDecision: 'EVENT_RISK', score: null } });
    expect(screen.getByText('dropped (was event risk)')).toBeInTheDocument();
  });

  it('says so when the ticker is already in the compare set', () => {
    setup({ compared: true });
    expect(screen.getByRole('button', { name: 'Remove from compare' })).toBeInTheDocument();
  });

  it('says a paused pick was held back by the regime gate, with the stored rule', () => {
    setup({
      row: {
        ...ROW,
        decision: 'PAUSED',
        reasons: 'regime=STRESS: vrp_scanner pauses in STRESS',
        flags: [],
      },
    });
    expect(screen.getByText('Paused')).toHaveAttribute('data-tone', 'warning');
    expect(screen.getByText(/The regime gate held this pick back/)).toBeVisible();
    expect(screen.getByText('regime=STRESS: vrp_scanner pauses in STRESS')).toBeVisible();
  });
});
