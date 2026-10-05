import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '@/shared/lib/testing';

import type { PreviewRow } from '../model/preview';
import { ScoreBreakdown } from './ScoreBreakdown';

const criterion = (id: string, outcome: string, penalty: number, normalised: number | null) => ({
  criterion_id: id,
  field: `feature.${id}`,
  mode: 'soft',
  value: 1,
  outcome,
  distance: null,
  normalised,
  penalty,
});

const row = (score: number, criteria: PreviewRow['criteria']): PreviewRow => ({
  instrument_id: 'EQ:KO',
  symbol: 'KO',
  rank: 3,
  decision: 'WATCH',
  score,
  flags: [],
  reasons: [],
  columns: {},
  criteria,
});

describe('ScoreBreakdown', () => {
  it('opens how the score was worked out', async () => {
    const { baseElement } = render(
      <ScoreBreakdown
        row={row(96, [criterion('iv30', 'PASS', 0, null), criterion('spread', 'NEAR', 4, 0.4)])}
        labelOf={(id) => (id === 'spread' ? 'Bid/ask spread' : id)}
      />,
    );
    await userEvent.click(screen.getByRole('button', { name: 'Score 96: how it was worked out' }));
    const panel = screen.getByRole('dialog', { name: 'How KO scored 96' });
    expect(panel).toHaveTextContent('100 − 4 in penalties');
    expect(panel).toHaveTextContent('Bid/ask spread');
    expect(panel).toHaveTextContent('near miss, 40% into the tolerance');
    expect(panel).toHaveTextContent('−4');
    expect(panel).toHaveTextContent('1 criterion passed with no penalty.');
    await expectNoA11yViolations(baseElement);
  });

  it('says a full score passed everything', async () => {
    render(<ScoreBreakdown row={row(100, [criterion('iv30', 'PASS', 0, null)])} />);
    await userEvent.click(screen.getByRole('button', { name: /Score 100/ }));
    expect(screen.getByRole('dialog')).toHaveTextContent('Every criterion passed: the full 100.');
  });
});
