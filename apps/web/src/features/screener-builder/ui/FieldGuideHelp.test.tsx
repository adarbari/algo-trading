import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type { CatalogueFeature, FieldGuide } from '@/entities/feature';
import { expectNoA11yViolations } from '@/shared/lib/testing';

import { FieldGuideHelp } from './FieldGuideHelp';

const FEATURE = {
  name: 'rollup.momentum@v1.rsi_14',
  dtype: 'float32',
  unit: 'pct_points',
  categories: [],
} as unknown as CatalogueFeature;
const GUIDE: FieldGuide = {
  theme: 'momentum and trend',
  reads: "Wilder's RSI over 14 sessions, 0 to 100.",
  uses: [
    {
      intent: 'oversold bounce',
      op: 'lt',
      value: 30,
      mode: 'soft',
      tolerance: 5,
      onMiss: null,
      note: 'with an uptrend gate',
    },
    {
      intent: 'momentum strength',
      op: 'gte',
      value: 50,
      mode: 'score',
      tolerance: 20,
      onMiss: null,
      note: '',
    },
  ],
  caveats: ['A pending takeover pins the price: RSI stays high with no trend behind it.'],
  sources: ['Wilder (1978)'],
};

describe('FieldGuideHelp', () => {
  it('opens on demand and shows the reading, the intents, the caveats and the sources', async () => {
    const onApply = vi.fn();
    const { container } = render(
      <FieldGuideHelp guide={GUIDE} feature={FEATURE} onApply={onApply} />,
    );
    expect(screen.queryByText(/Wilder's RSI/)).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: 'How to read it' }));
    expect(screen.getByText(/Wilder's RSI/)).toBeInTheDocument();
    expect(screen.getByText('< 30')).toBeInTheDocument();
    expect(
      screen.getByText(/soft, a near miss within 5 · with an uptrend gate/),
    ).toBeInTheDocument();
    expect(screen.getByText(/pending takeover/)).toBeInTheDocument();
    expect(screen.getByText(/Sources: Wilder \(1978\)/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Use: momentum strength' }));
    expect(onApply).toHaveBeenCalledWith(GUIDE.uses[1]);
    await expectNoA11yViolations(container);
  });

  it('is read-only when disabled', async () => {
    render(<FieldGuideHelp guide={GUIDE} feature={FEATURE} onApply={vi.fn()} disabled />);
    await userEvent.click(screen.getByRole('button', { name: 'How to read it' }));
    expect(screen.getByRole('button', { name: 'Use: oversold bounce' })).toBeDisabled();
  });
});
