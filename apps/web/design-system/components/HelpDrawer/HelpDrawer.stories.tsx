import type { Meta, StoryObj } from '@storybook/react-vite';
import { useState } from 'react';
import { waitFor } from 'storybook/test';

import { Mono } from '../../primitives/Mono';
import { Stack } from '../../primitives/Stack';
import { Surface } from '../../primitives/Surface';
import { Text } from '../../primitives/Text';
import { Button } from '../Button';
import { ErrorState } from '../ErrorState';
import { InfoButton } from '../InfoButton';
import { Skeleton } from '../Skeleton';
import { HelpDrawer, HelpLead, HelpSection, type HelpDrawerProps } from './HelpDrawer';

/** The opener (an InfoButton) and its drawer, as an app wires them. */
function Example(props: HelpDrawerProps) {
  const [open, setOpen] = useState(props.open);
  return (
    <Stack direction="row" gap={1} align="center">
      <Text weight="medium">rel_volume</Text>
      <InfoButton
        label="What is rel_volume?"
        expanded={open}
        onClick={() => {
          setOpen(true);
        }}
      />
      <HelpDrawer {...props} open={open} onOpenChange={setOpen} />
    </Stack>
  );
}

const fullPage = (
  <Button variant="ghost" size="sm" iconEnd="chevron-right">
    Open full page
  </Button>
);

/** One "Use it for" card: the intent, its rule in mono, a note and the action. */
function UseCard({ intent, rule, note }: { intent: string; rule: string; note?: string }) {
  return (
    <Surface tone="row" border="all" radius="lg" padding={3}>
      <Stack gap={2}>
        <Text weight="medium">{intent}</Text>
        <Text size="sm" tone="accent" mono>
          {rule}
        </Text>
        {note && (
          <Text size="sm" tone="muted">
            {note}
          </Text>
        )}
        <span>
          <Button variant="ghost" size="sm" icon="plus">
            Add to Builder
          </Button>
        </span>
      </Stack>
    </Surface>
  );
}

const meta = {
  title: 'Components/HelpDrawer',
  component: HelpDrawer,
  args: {
    open: true,
    onOpenChange: () => undefined,
    eyebrow: 'rollup.momentum@v1.rel_volume',
    title: 'Relative volume',
    meta: 'Momentum and trend · ratio · nightly',
    fullPage,
    children: null,
  },
  render: (args) => <Example {...args} />,
  parameters: {
    states: {
      notApplicable: {
        Empty: 'an explanation that does not exist has no button to open it',
      },
    },
  },
} satisfies Meta<typeof HelpDrawer>;

export default meta;
type Story = StoryObj<typeof meta>;

/** The least an explanation needs: a title and the lead paragraph. */
export const Default: Story = {
  args: {
    eyebrow: undefined,
    meta: undefined,
    children: (
      <HelpLead>
        The session’s volume over the average of the 20 sessions before it: 1 is normal, 2 is twice
        normal, 0.5 is a quiet day.
      </HelpLead>
    ),
  },
};

/** A catalogue field: how to read it, two ways to use it, the caveat count. */
export const Field: Story = {
  args: {
    children: (
      <>
        <HelpLead>
          The session’s volume over the average of the 20 sessions before it: 1 is normal, 2 is
          twice normal, 0.5 is a quiet day. Above 1.5 is the usual confirmation that a move has
          participation behind it; above 2 is strong; above 5 is an event. Below 0.7 on an up day is
          a move nobody joined.
        </HelpLead>
        <HelpSection title="Use it for">
          <Stack gap={2}>
            <UseCard intent="Heavy volume today" rule="gte 1.5 · soft · tolerance 0.3" />
            <UseCard
              intent="An unusual volume event"
              rule="gte 3 · soft · tolerance 0.5"
              note="Most 3x days are earnings or index events."
            />
          </Stack>
        </HelpSection>
        <Text size="sm" tone="warning">
          4 caveats · fooled by 3 situations
        </Text>
      </>
    ),
  },
};

/** A regime indicator: plain-language question as the title, a label as the eyebrow. */
export const RegimeIndicator: Story = {
  args: {
    eyebrow: 'Market regime · slow signal',
    title: 'Are long-term rates below short-term ones?',
    meta: '10-year minus 3-month Treasury spread (T10Y3M)',
    fullPage: (
      <Button variant="ghost" size="sm" iconEnd="chevron-right">
        Open full page
      </Button>
    ),
    children: (
      <>
        <HelpLead>
          Normally lenders want more to lend for longer. When the 10-year pays less than the 3-month
          bill, markets expect the Fed to cut because the economy will weaken, and banks earn less
          on new loans.
        </HelpLead>
        <HelpSection title="When it is on">
          <Text as="p" tone="secondary">
            On when the gap has been below zero for a month or more. The return to a positive gap
            after a long inversion is the later, more urgent warning.
          </Text>
        </HelpSection>
        <Stack direction="row" gap={4} wrap>
          <Stack gap={1}>
            <Text size="sm" tone="muted">
              Lead time
            </Text>
            <Text>6 to 18 months before a recession.</Text>
          </Stack>
          <Stack gap={1}>
            <Text size="sm" tone="muted">
              Track record
            </Text>
            <Text>
              Warned before all 8 recessions since 1969; false alarms in 1998 and 2022-24.
            </Text>
          </Stack>
        </Stack>
      </>
    ),
  },
};

/** The explanation is still being fetched: the header is known, the body is a Skeleton. */
export const Loading: Story = {
  args: { children: <Skeleton lines={5} label="Loading the explanation…" /> },
};

/** The explanation could not be loaded; the full page link still works. */
export const Error: Story = {
  args: {
    children: (
      <ErrorState
        title="This explanation could not be loaded."
        message="The Guide did not answer. Try again, or open the full page."
        detail="GRAPHQL_TIMEOUT"
        onRetry={() => undefined}
      />
    ),
  },
};

/** Settles the scroll of a dialog whose body scrolled to its first focusable control. */
const scrolledToTop = async () => {
  const dialog = await waitFor((): HTMLElement => {
    const found = document.querySelector<HTMLElement>('[role="dialog"]');
    if (!found) throw new TypeError('no dialog yet');
    return found;
  });
  // Focus moves to the first control after open and scrolls the body by a timing-dependent
  // amount; the screenshot shows the top of the body instead.
  await new Promise((resolve) => {
    requestAnimationFrame(() => {
      requestAnimationFrame(resolve);
    });
  });
  for (const element of dialog.querySelectorAll<HTMLElement>('*')) {
    if (element.scrollHeight > element.clientHeight && element.scrollTop > 0) element.scrollTop = 0;
  }
};

/** Long text and many sections: the body scrolls, the header and footer stay put. */
export const Dense: Story = {
  play: scrolledToTop,
  args: {
    children: (
      <>
        <HelpLead>
          The session’s volume over the average of the 20 sessions before it: 1 is normal, 2 is
          twice normal, 0.5 is a quiet day. Above 1.5 is the usual confirmation that a move has
          participation behind it; above 2 is strong; above 5 is an event. Below 0.7 on an up day is
          a move nobody joined.
        </HelpLead>
        <HelpSection title="When it lies">
          <Stack gap={2}>
            <Text as="p" tone="secondary">
              Quarterly expiry Fridays, the Russell reconstitution (late June) and index inclusions
              multiply volume without any news; so do secondary offerings and block trades. High
              volume with a flat close (<Mono>rollup.momentum@v1.ret_5d</Mono> near 0) is usually
              one of these.
            </Text>
            <Text as="p" tone="secondary">
              Earnings days are 3 to 10 times normal volume by nature; check{' '}
              <Mono>rollup.earnings@v1.last_earnings_date</Mono> before reading a spike as unusual.
            </Text>
            <Text as="p" tone="secondary">
              On thin names a single institutional order is a 5x day; gate on{' '}
              <Mono>rollup.price_stats@v2.adv_usd_20d</Mono>.
            </Text>
            <Text as="p" tone="secondary">
              The base is the 20 sessions before today; after a very heavy week the base is inflated
              and today’s ratio understates activity.
            </Text>
          </Stack>
        </HelpSection>
        <HelpSection title="Use it for">
          <Stack gap={2}>
            <UseCard intent="Heavy volume today" rule="gte 1.5 · soft · tolerance 0.3" />
            <UseCard
              intent="An unusual volume event"
              rule="gte 3 · soft · tolerance 0.5"
              note="Check rollup.earnings@v1.last_earnings_date; most 3x days are earnings or index events."
            />
          </Stack>
        </HelpSection>
        <HelpSection title="Sources">
          <Text as="p" size="sm" tone="muted">
            Volume confirmation thresholds: luxalgo.com, “How volume confirms breakouts in trading”.
          </Text>
        </HelpSection>
      </>
    ),
  },
};
