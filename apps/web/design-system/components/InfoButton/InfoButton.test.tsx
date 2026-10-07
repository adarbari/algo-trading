import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { InfoButton } from './InfoButton';

describe('InfoButton', () => {
  it('is named by its label and calls onClick', async () => {
    const onClick = vi.fn();
    render(<InfoButton label="What is rel_volume?" onClick={onClick} />);
    const button = screen.getByRole('button', { name: 'What is rel_volume?' });
    expect(button).not.toHaveAttribute('aria-expanded');
    await userEvent.click(button);
    expect(onClick).toHaveBeenCalledOnce();
  });

  it('reports whether its explanation is open', () => {
    const { rerender } = render(<InfoButton label="What is rel_volume?" expanded={false} />);
    expect(screen.getByRole('button')).toHaveAttribute('aria-expanded', 'false');
    rerender(<InfoButton label="What is rel_volume?" expanded />);
    expect(screen.getByRole('button')).toHaveAttribute('aria-expanded', 'true');
  });

  it('shows the summary as its description on keyboard focus', async () => {
    render(
      <InfoButton label="What is rel_volume?" summary="Volume over its 20-session average." />,
    );
    await userEvent.tab();
    const tip = await screen.findByRole('tooltip');
    expect(tip).toHaveTextContent('Volume over its 20-session average.');
    expect(screen.getByRole('button')).toHaveAccessibleDescription(
      'Volume over its 20-session average.',
    );
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <>
        <InfoButton label="What is rel_volume?" />
        <InfoButton
          label="What is atr_ratio_5_20?"
          summary="Short over long volatility."
          expanded
        />
      </>,
    );
    await expectNoA11yViolations(container);
  });
});
