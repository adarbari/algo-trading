import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { InfoButton } from '../InfoButton';
import { OddsLine } from './OddsLine';

const READY = { hitRate: 0.62, baseRate: 0.51, sessions: 118 };

describe('OddsLine', () => {
  it('writes the win rate against the base rate, with the trades', () => {
    const { container } = render(<OddsLine {...READY} />);
    expect(container.textContent).toContain('62.0%');
    expect(container.textContent).toContain('vs 51.0% base');
    expect(container.textContent).toContain('118');
    expect(screen.queryByText('EXPLORATORY')).not.toBeInTheDocument();
  });

  it('shows lift, picks and the run label only when given', () => {
    const { container } = render(
      <OddsLine
        {...READY}
        liftPts={11}
        picks={340}
        runLabel="run 7"
        info={<InfoButton label="Help" />}
      />,
    );
    expect(container.textContent).toContain('+11 pts');
    expect(container.textContent).toContain('340');
    expect(container.textContent).toContain('run 7');
    expect(screen.getByRole('button', { name: 'Help' })).toBeInTheDocument();
  });

  it('labels an exploratory run', () => {
    render(<OddsLine {...READY} exploratory />);
    expect(screen.getByText('EXPLORATORY')).toBeInTheDocument();
  });

  it('shows loading, empty and error states with no figures', () => {
    const { rerender, container } = render(<OddsLine state="loading" />);
    expect(screen.getByRole('status')).toHaveAttribute('aria-busy', 'true');
    rerender(<OddsLine state="empty" />);
    expect(screen.getByText('No run yet')).toBeInTheDocument();
    rerender(<OddsLine state="error" message="Odds are down" />);
    expect(screen.getByRole('alert')).toHaveTextContent('Odds are down');
    expect(container.textContent).not.toContain('%');
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<OddsLine {...READY} liftPts={11} picks={3} exploratory />);
    await expectNoA11yViolations(container);
  });
});
