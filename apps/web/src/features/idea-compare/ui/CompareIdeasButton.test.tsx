import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '@/shared/lib/testing';

import { CompareIdeasButton } from './CompareIdeasButton';

describe('CompareIdeasButton', () => {
  it('is disabled until something is selected', async () => {
    const { container } = render(<CompareIdeasButton symbols={[]} onCompare={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'Compare selected' })).toBeDisabled();
    await expectNoA11yViolations(container);
  });

  it('opens the selection in Explore', async () => {
    const onCompare = vi.fn();
    render(<CompareIdeasButton symbols={['MSFT', 'AAPL']} onCompare={onCompare} />);
    await userEvent.click(screen.getByRole('button', { name: 'Compare selected (2)' }));
    expect(onCompare).toHaveBeenCalledWith({ sel: 'MSFT,AAPL', focus: 'MSFT' });
  });

  it('says when only the first six are compared', () => {
    render(
      <CompareIdeasButton symbols={['A', 'B', 'C', 'D', 'E', 'F', 'G']} onCompare={vi.fn()} />,
    );
    expect(
      screen.getByRole('button', { name: 'Compare the first 6 of 7 selected in Explore' }),
    ).toBeInTheDocument();
  });
});
