import type { Meta, StoryObj } from '@storybook/react-vite';
import { useState } from 'react';

import { SearchDialog, type SearchDialogProps } from './SearchDialog';

/** The query is editable; the results are the story's. */
function Example(props: SearchDialogProps) {
  const [query, setQuery] = useState(props.query);
  return <SearchDialog {...props} query={query} onQueryChange={setQuery} />;
}

const meta = {
  title: 'Components/SearchDialog',
  component: SearchDialog,
  args: {
    open: true,
    onOpenChange: () => undefined,
    onSelect: () => undefined,
    onQueryChange: () => undefined,
    title: 'Search the Guide',
    placeholder: 'Search fields, playbooks, terms',
    query: 'volume',
    hint: 'Type a field name, a playbook or a word the app uses.',
    groups: [
      {
        id: 'field',
        title: 'Fields',
        items: [
          {
            id: 'rollup.momentum@v1.rel_volume',
            title: 'rollup.momentum@v1.rel_volume',
            snippet: 'Today volume over its 20-day average. Above 2 is heavy.',
            href: '/guide/fields/rollup.momentum@v1.rel_volume',
          },
          {
            id: 'price_stats@v1.adv_usd_20d',
            title: 'price_stats@v1.adv_usd_20d',
            snippet: 'Average dollar volume over 20 sessions.',
            href: '/guide/fields/price_stats@v1.adv_usd_20d',
          },
        ],
      },
      {
        id: 'term',
        title: 'Glossary',
        items: [
          {
            id: 'liquidity_risk',
            title: 'LIQUIDITY_RISK',
            snippet: 'A hit whose volume is thin for the size you would trade.',
            href: '/guide/glossary/liquidity_risk',
          },
        ],
      },
    ],
  },
  render: (args) => <Example {...args} />,
  parameters: {
    states: {
      notApplicable: {
        Dense: 'the dialog takes the density tokens for its rows; there is no denser variant',
      },
    },
  },
} satisfies Meta<typeof SearchDialog>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

/** Before anything is typed: the hint. */
export const Idle: Story = { args: { query: '', groups: [] } };

/** The first read, nothing to show yet. */
export const Loading: Story = { args: { groups: [], loading: true } };

/** A query nothing matches. */
export const Empty: Story = { args: { query: 'zzzz', groups: [] } };

export const Error: Story = { args: { groups: [], error: true, onRetry: () => undefined } };
