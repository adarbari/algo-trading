import type { Meta, StoryObj } from '@storybook/react-vite';

import { narrow } from '../../testing';
import { Button } from '../Button';
import { Chip } from '../Chip';
import { Field } from '../Field';
import { FilterGroupButton } from '../FilterGroupButton';
import { OptionList } from '../OptionList';
import { SearchInput } from '../SearchInput';
import { Select } from '../Select';
import { FilterBar } from './FilterBar';

const noop = () => undefined;

const meta = {
  title: 'Components/FilterBar',
  component: FilterBar,
  args: {
    search: <SearchInput aria-label="Search tickers" placeholder="Search tickers" />,
    quick: (
      <>
        <Chip label="Near 52w high" onSelectedChange={noop} />
        <Chip label="Liquid" defaultSelected onSelectedChange={noop} />
      </>
    ),
    more: (
      <>
        <Field label="Sector">
          <Select
            options={[
              { value: 'tech', label: 'Technology' },
              { value: 'energy', label: 'Energy' },
            ]}
            placeholder="Any sector"
          />
        </Field>
        <Field label="Liquidity">
          <Select
            options={[
              { value: 'high', label: 'High' },
              { value: 'low', label: 'Low' },
            ]}
            placeholder="Any"
          />
        </Field>
      </>
    ),
    activeCount: 0,
  },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'FilterBar lays out the controls it is given; the table shows loading',
        Empty: 'a table with nothing to filter renders no FilterBar',
        Error: 'FilterBar cannot fail',
        Dense: 'FilterBar follows the density tokens of its controls',
      },
    },
  },
} satisfies Meta<typeof FilterBar>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Wide: the search, the quick chips and the "+ Filter" popover. */
export const Default: Story = {};

/** Two many-valued filters in force, shown as removable chips. */
export const WithActive: Story = {
  args: {
    activeCount: 2,
    active: (
      <>
        <Chip label="Sector: Technology" onRemove={noop} />
        <Chip label="Liquidity: High" onRemove={noop} />
      </>
    ),
  },
};

/** No many-valued filters: no "+ Filter" trigger. */
export const NoMore: Story = { args: { more: undefined } };

/**
 * A phone (375 px), the sheet proposal: the search and a "Filters · N" button on one row, the
 * active chips scrolling under it. The owner's choice against `NarrowScroll` (ADR 0011).
 */
export const Narrow: Story = {
  decorators: [narrow],
  args: { ...WithActive.args, narrow: 'sheet' },
};

/** The sheet proposal with the filters sheet open. The owner's choice (ADR 0011). */
export const NarrowOpen: Story = {
  ...Narrow,
  args: { ...Narrow.args, defaultOpen: true },
};

/**
 * A phone (375 px), the scroll proposal: the search, then one row scrolling sideways with the
 * "+ Filter" trigger first. The owner's choice against `Narrow` (ADR 0011).
 */
export const NarrowScroll: Story = {
  decorators: [narrow],
  args: { ...WithActive.args, narrow: 'scroll' },
};

const groups = (
  <>
    <FilterGroupButton label="Setup" activeCount={2}>
      <OptionList
        label="Decision"
        value={null}
        values={['QUALIFIED']}
        onSelect={noop}
        items={[
          { id: 'QUALIFIED', title: 'Qualified', count: 41 },
          { id: 'WATCH', title: 'Watch', count: 12 },
        ]}
      />
    </FilterGroupButton>
    <FilterGroupButton label="What changed">x</FilterGroupButton>
    <FilterGroupButton label="Tradeable">x</FilterGroupButton>
    <FilterGroupButton label="Coming up">x</FilterGroupButton>
  </>
);

const actions = (
  <>
    <Button size="sm" variant="ghost">
      Clear all
    </Button>
    <Button size="sm" variant="ghost">
      Save view
    </Button>
  </>
);

/** The ADR 0082 toolbar: search, group buttons and More filters on one row; chips; count line with actions. */
export const WithGroups: Story = {
  args: {
    quick: undefined,
    groups,
    actions,
    count: '12 of 340',
    activeCount: 2,
    active: (
      <>
        <Chip label="Decision Qualified" onRemove={noop} />
        <Chip label="DTE ..14" onRemove={noop} />
      </>
    ),
  },
};

/** The groups, a count and the sheet's "Show N results" button at 375 px. */
export const NarrowGroups: Story = {
  decorators: [narrow],
  args: { ...WithGroups.args, applyLabel: 'Show 12 results' },
};

/** The same with the sheet open: groups in the sheet and the footer button. */
export const NarrowGroupsOpen: Story = {
  ...NarrowGroups,
  args: { ...NarrowGroups.args, defaultOpen: true },
};
