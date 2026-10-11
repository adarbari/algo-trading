import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { FormulaPreview } from './FormulaPreview';

const props = {
  name: 'draft_near_52w_high',
  formula: 'close / price_stats.high_52w - 1',
  inputs: 'Inputs: close, price_stats.high_52w',
  statsLabel: 'Dry run',
  stats: [
    { label: 'Rows checked', value: '13,334' },
    { label: 'Passing', value: '612' },
  ],
  sample: {
    label: 'Sample rows',
    labelHeader: 'Symbol',
    columns: [{ id: 'value', header: 'value' }],
    rows: [
      { id: 'JPM', label: 'JPM', values: { value: -0.022 } },
      { id: 'AAPL', label: 'AAPL', values: { value: null } },
    ],
  },
};

describe('FormulaPreview', () => {
  it('shows the formula, the inputs line, the stats and the actions', () => {
    render(<FormulaPreview {...props} actions={<button type="button">Review and add</button>} />);
    expect(screen.getByText('close / price_stats.high_52w - 1').tagName).toBe('CODE');
    expect(screen.getByText('Inputs: close, price_stats.high_52w')).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Dry run' })).toBeInTheDocument();
    expect(screen.getByText('13,334').tagName).toBe('DD');
    expect(screen.getByRole('button', { name: 'Review and add' })).toBeInTheDocument();
  });

  it('shows a sample table, and none without rows', () => {
    const { rerender } = render(<FormulaPreview {...props} />);
    expect(screen.getByRole('grid', { name: 'Sample rows' })).toBeInTheDocument();
    rerender(<FormulaPreview {...props} sample={undefined} />);
    expect(screen.queryByRole('grid', { name: 'Sample rows' })).toBeNull();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<FormulaPreview {...props} />);
    await expectNoA11yViolations(container);
  });
});
