import type { Meta, StoryObj } from '@storybook/react-vite';

import { Stack } from '../../primitives/Stack';
import { Text } from '../../primitives/Text';
import { TextLink } from './TextLink';

const meta = {
  title: 'Components/TextLink',
  component: TextLink,
  args: { href: '/guide/fields/rel_volume', children: 'Relative volume' },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'a link is static text; it never loads',
        Empty: 'a link always has its words',
        Error: 'a link cannot fail; the page it opens shows its own errors',
      },
    },
  },
} satisfies Meta<typeof TextLink>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

/** The Guide link in the top bar: icon, text, the key that opens it; marked while on the Guide. */
export const UtilityWithKey: Story = {
  args: { href: '/guide', children: 'Guide', icon: 'book', keys: ['?'], current: true },
};

/** A catalogue name in a list of links, in the mono face and the quiet colour. */
export const CatalogueName: Story = {
  args: { href: '/guide/fields/ret_5d', children: 'ret_5d', mono: true, tone: 'secondary' },
};

/** Inside a sentence the link takes the surrounding size; dense lists use `sm`. */
export const Dense: Story = {
  render: () => (
    <Stack gap={2}>
      <Text as="p" size="sm">
        Check{' '}
        <TextLink href="/guide/fields/last_earnings_date" mono size="inherit">
          last_earnings_date
        </TextLink>{' '}
        before reading a spike as unusual.
      </Text>
      <TextLink href="#reads" size="sm">
        How to read it
      </TextLink>
    </Stack>
  ),
};
