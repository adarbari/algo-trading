import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { Chip } from './Chip';

describe('Chip', () => {
  it('is plain text without handlers', () => {
    render(<Chip label="ADR" />);
    expect(screen.getByText('ADR')).toBeInTheDocument();
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('toggles as a pressed button', async () => {
    const onSelectedChange = vi.fn();
    render(<Chip label="Watchlist" onSelectedChange={onSelectedChange} />);
    const chip = screen.getByRole('button', { name: 'Watchlist' });
    expect(chip).toHaveAttribute('aria-pressed', 'false');
    await userEvent.click(chip);
    expect(chip).toHaveAttribute('aria-pressed', 'true');
    expect(onSelectedChange).toHaveBeenCalledWith(true);
  });

  it('removes with a button named for the chip', async () => {
    const onRemove = vi.fn();
    render(<Chip label="Sector: Energy" onRemove={onRemove} />);
    await userEvent.click(screen.getByRole('button', { name: 'Remove Sector: Energy' }));
    expect(onRemove).toHaveBeenCalledOnce();
  });

  it('acts as the dashed add button', async () => {
    const onClick = vi.fn();
    render(<Chip label="Filter" icon="plus" variant="dashed" onClick={onClick} />);
    await userEvent.click(screen.getByRole('button', { name: 'Filter' }));
    expect(onClick).toHaveBeenCalledOnce();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <>
        <Chip label="On" selected onSelectedChange={vi.fn()} />
        <Chip label="Tag" onRemove={vi.fn()} />
        <Chip label="Add" variant="dashed" onClick={vi.fn()} />
      </>,
    );
    await expectNoA11yViolations(container);
  });
});
