import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '@/shared/lib/testing';

import { CriteriaScorecard } from './CriteriaScorecard';

vi.mock('@/entities/feature', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useFeatureCatalogue: () => ({
    data: [
      { name: 'rollup.iv30@v1.iv30', unit: 'decimal', dtype: 'float64', description: 'IV30' },
      { name: 'feature.iv_hv_ratio', unit: 'ratio', dtype: 'float64', description: 'IV30 / HV30' },
    ],
  }),
}));
vi.mock('../api/runs', () => ({
  useScreenerRuns: () => ({
    data: {
      // The typed criteria of the `Screener`: op and threshold as the config states them.
      byId: new Map([
        [
          'vrp',
          {
            criteria: [
              { id: 'iv30', field: 'rollup.iv30@v1.iv30', mode: 'hard', op: 'gte', value: 0.5 },
              { id: 'ratio', field: 'feature.iv_hv_ratio', mode: 'soft', op: 'gte', value: 1.25 },
            ],
          },
        ],
      ]),
    },
  }),
}));

const ENTRIES = [
  { id: 'optionable', field: 'instrument.optionable', outcome: 'PASS', value: true },
  { id: 'iv30', field: 'rollup.iv30@v1.iv30', outcome: 'PASS', value: 1.11 },
  {
    id: 'ratio',
    field: 'feature.iv_hv_ratio',
    outcome: 'NEAR',
    value: 1.08,
    distance: 0.1700000001,
  },
  { id: 'gone', field: 'rollup.iv30@v1.iv30', outcome: 'MISSING' },
];

describe('CriteriaScorecard', () => {
  it('lists each criterion with its value, rule, distance and outcome (not the gates)', async () => {
    const { container } = render(<CriteriaScorecard screenerId="vrp" entries={ENTRIES} />);
    const list = screen.getByLabelText('Criteria');
    expect(list).not.toHaveTextContent(/optionable/i);
    expect(list).toHaveTextContent('111.0%');
    expect(list).toHaveTextContent('≥ 50%');
    expect(list).toHaveTextContent('1.08');
    expect(list).toHaveTextContent('≥ 1.25');
    expect(list).toHaveTextContent('short by 0.17');
    expect(list).toHaveTextContent('Passed');
    expect(list).toHaveTextContent('Near miss');
    expect(list).toHaveTextContent('No value');
    expect(screen.getByText('Near miss')).toHaveAttribute('data-tone', 'warning');
    await expectNoA11yViolations(container);
  });

  it('says so when there is nothing to show', () => {
    render(<CriteriaScorecard screenerId="vrp" entries={[]} />);
    expect(screen.getByText('No criteria.')).toBeInTheDocument();
  });
});
