import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { Chip } from '../Chip';
import { Field } from '../Field';
import { SearchInput } from '../SearchInput';
import { Select } from '../Select';
import { FilterBar, type FilterBarProps } from './FilterBar';

function Bar(props: Partial<FilterBarProps>) {
  return (
    <FilterBar
      search={<SearchInput aria-label="Search tickers" />}
      quick={<Chip label="Near 52w high" onSelectedChange={() => undefined} />}
      active={<Chip label="Sector: Technology" onRemove={() => undefined} />}
      more={
        <Field label="Sector">
          <Select options={[{ value: 'tech', label: 'Technology' }]} placeholder="Any sector" />
        </Field>
      }
      {...props}
    />
  );
}

describe('FilterBar', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('shows every slot wide, the fields behind the "+ Filter" popover', async () => {
    vi.stubGlobal('innerWidth', 1400);
    const { container } = render(<Bar />);
    expect(screen.getByRole('searchbox', { name: 'Search tickers' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Near 52w high' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Remove Sector: Technology' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Filters/ })).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: 'Filter' }));
    expect(
      within(screen.getByRole('dialog', { name: 'More filters' })).getByLabelText('Sector'),
    ).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it('has no trigger without `more`', () => {
    vi.stubGlobal('innerWidth', 1400);
    render(<Bar more={undefined} />);
    expect(screen.queryByRole('button', { name: 'Filter' })).toBeNull();
  });

  it('narrow: a Filters button with the count opens a sheet with the quick chips and fields', async () => {
    vi.stubGlobal('innerWidth', 375);
    const { container } = render(<Bar activeCount={2} />);
    const button = screen.getByRole('button', { name: 'Filters · 2' });
    expect(screen.getByRole('button', { name: 'Remove Sector: Technology' })).toBeInTheDocument();
    await userEvent.click(button);
    const sheet = screen.getByRole('dialog', { name: 'Filters' });
    expect(within(sheet).getByRole('button', { name: 'Near 52w high' })).toBeInTheDocument();
    expect(within(sheet).getByLabelText('Sector')).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it('narrow: the button is just "Filters" with no filter in force', () => {
    vi.stubGlobal('innerWidth', 375);
    render(<Bar activeCount={0} />);
    expect(screen.getByRole('button', { name: 'Filters' })).toBeInTheDocument();
  });

  it('narrow scroll: one row with the trigger, the quick and the active chips', async () => {
    vi.stubGlobal('innerWidth', 375);
    const { container } = render(<Bar narrow="scroll" />);
    expect(screen.queryByRole('button', { name: /^Filters/ })).toBeNull();
    expect(screen.getByRole('button', { name: 'Filter' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Near 52w high' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Remove Sector: Technology' })).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });
});
