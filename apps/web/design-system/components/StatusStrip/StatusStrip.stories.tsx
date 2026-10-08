import type { Meta, StoryObj } from '@storybook/react-vite';

import { narrow } from '../../testing';
import { Button } from '../Button';
import { StatusStrip, type StatusIssue } from './StatusStrip';

const ISSUES: StatusIssue[] = [
  {
    id: 'run:market-daily:ibkr-iv',
    severity: 'failing',
    title: 'Ingestion: market-daily failed at step "ibkr-iv"',
    detail: 'Held back all screens for 2026-10-08. Needs a retry or a waive.',
    actions: (
      <>
        <Button size="sm" variant="ghost">
          View run
        </Button>
        <Button size="sm" variant="ghost">
          Retry
        </Button>
      </>
    ),
  },
  {
    id: 'screen:vol-premium',
    severity: 'warning',
    title: 'Screener "Vol premium sellers" has no run for today',
    detail: 'It needs the IBKR IV table, which did not land.',
    actions: (
      <Button size="sm" variant="ghost">
        Open screener
      </Button>
    ),
  },
  {
    id: 'llm:key',
    severity: 'warning',
    title: 'LLM key not configured',
    detail: 'Describe-a-screen is off.',
  },
];

const meta = {
  title: 'Components/StatusStrip',
  component: StatusStrip,
  args: { issues: ISSUES, onSnooze: () => undefined },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'the strip shows only issues that are known; while sources load it is absent',
      },
    },
  },
} satisfies Meta<typeof StatusStrip>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Collapsed: severity pills, the most serious message and "and N more". */
export const Default: Story = {};

/** The full list, each issue with its detail, actions and snooze. */
export const Expanded: Story = { args: { defaultExpanded: true } };

/** No issue and no `allClear`: nothing is rendered. */
export const Empty: Story = { args: { issues: [] } };

/** No issue with the slim green line. */
export const AllClear: Story = { args: { issues: [], allClear: 'All systems normal' } };

/** One failing issue, open. */
export const Error: Story = {
  args: { issues: ISSUES.slice(0, 1), defaultExpanded: true },
};

/** One warning, collapsed: a single pill and no "and N more". */
export const Dense: Story = { args: { issues: ISSUES.slice(1, 2) } };

/** A phone-width container (375 px): the "and N more" drops, the actions sit under the text. */
export const Narrow: Story = { decorators: [narrow], args: { defaultExpanded: true } };
