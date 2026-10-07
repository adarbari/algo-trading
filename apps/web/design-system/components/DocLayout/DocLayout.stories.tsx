import type { Meta, StoryObj } from '@storybook/react-vite';

import { Heading } from '../../primitives/Heading';
import { Text } from '../../primitives/Text';
import { NavList } from '../NavList';
import { DocLayout, DocSection } from './DocLayout';

const rail = (
  <NavList
    aria-label="Guide"
    items={[
      { href: '/guide', label: 'Start here' },
      { href: '/guide/fields', label: 'Fields', count: 399, current: true },
    ]}
  />
);
const aside = (
  <NavList
    aria-label="On this page"
    size="sm"
    items={[
      { href: '#reads', label: 'How to read it', current: true },
      { href: '#use', label: 'Use it for' },
    ]}
  />
);

const meta = {
  title: 'Components/DocLayout',
  component: DocLayout,
  args: {
    rail,
    aside,
    children: (
      <>
        <DocSection id="reads">
          <Heading level={1}>Relative volume</Heading>
          <Text as="p" size="xl">
            The session’s volume over the average of the 20 sessions before it.
          </Text>
        </DocSection>
        <DocSection id="use">
          <Heading level={2}>Use it for</Heading>
          <Text as="p">Heavy volume today: gte 1.5.</Text>
        </DocSection>
      </>
    ),
  },
  parameters: {
    layout: 'fullscreen',
    states: {
      notApplicable: {
        Loading: 'the frame is layout only; its contents show their own loading states',
        Empty: 'the frame is layout only; its contents show their own empty states',
        Error: 'the frame is layout only; its contents show their own errors',
      },
    },
  },
} satisfies Meta<typeof DocLayout>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

/** No end list (a section's home page): the article is wider. */
export const RailOnly: Story = { args: { aside: undefined } };

/** Phone width: the rail, the article and the list stack. */
export const Dense: Story = {
  decorators: [
    (Story) => (
      <div style={{ maxWidth: 'var(--size-sidebar)' }}>
        <Story />
      </div>
    ),
  ],
};
