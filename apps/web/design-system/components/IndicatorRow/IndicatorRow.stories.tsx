import type { Meta, StoryObj } from '@storybook/react-vite';

import { Stack } from '../../primitives/Stack';
import { Text } from '../../primitives/Text';
import type { StatusTone } from '../StatusBadge';
import { IndicatorRow, type IndicatorChange } from './IndicatorRow';

/** The detail of an expandable row: why it matters, what it did before, a link. Sample text. */
const DETAIL = (
  <>
    <Text size="sm">
      Banks tighten lending before recessions, so credit dries up for firms that rely on it.
    </Text>
    <Text size="sm" tone="secondary">
      Before: tightened through 2007, again in early 2020 and in 2022. Gave two false alarms.
    </Text>
    <Text size="sm" tone="accent">
      Learn more: Federal Reserve survey page
    </Text>
  </>
);

const meta = {
  title: 'Components/IndicatorRow',
  component: IndicatorRow,
  args: {
    status: { tone: 'warning', label: 'On' },
    name: 'Are banks still lending?',
    technicalName: 'Senior loan officer survey',
    description: 'Net share of banks tightening credit standards for firms.',
    value: 21.4,
    format: { kind: 'number', digits: 1 },
    unit: '%',
    changed: 'up',
    children: DETAIL,
    defaultOpen: true,
  },
  parameters: {
    states: {
      notApplicable: {
        Empty: 'a list with no indicators shows its own empty state; a row always has a name',
        Error: 'a row shows values it is given; the list around it shows a failed load',
      },
    },
  },
} satisfies Meta<typeof IndicatorRow>;

export default meta;
type Story = StoryObj<typeof meta>;

/** An expandable row, open: the header is one button; the detail renders its children. */
export const Default: Story = {};

/** The same row collapsed, as it sits in a list. */
export const Collapsed: Story = { args: { defaultOpen: false } };

interface Sample {
  tone: StatusTone;
  label: string;
  name: string;
  technicalName: string;
  value: number | null;
  unit?: string;
  changed?: IndicatorChange;
}

const SAMPLES: Sample[] = [
  {
    tone: 'negative',
    label: 'On',
    name: 'Are credit spreads widening?',
    technicalName: 'HY OAS',
    value: 142,
    unit: 'bp',
    changed: 'new',
  },
  {
    tone: 'warning',
    label: 'On',
    name: 'Are banks still lending?',
    technicalName: 'SLOOS',
    value: 21.4,
    unit: '%',
    changed: 'up',
  },
  {
    tone: 'positive',
    label: 'Off',
    name: 'Is the labour market cracking?',
    technicalName: 'Sahm rule',
    value: 0.2,
    unit: 'pts',
    changed: 'down',
  },
  {
    tone: 'neutral',
    label: 'Unknown',
    name: 'Is the yield curve inverted?',
    technicalName: '10y-3m',
    value: null,
  },
];

/** No children: plain rows with no chevron, text lined up with expandable rows. Each tone and marker. */
export const Flat: Story = {
  render: (args) => (
    <Stack gap={0}>
      {SAMPLES.map(({ tone, label, name, technicalName, value, unit, changed }) => (
        <IndicatorRow
          key={name}
          status={{ tone, label }}
          name={name}
          technicalName={technicalName}
          value={value}
          {...(unit === undefined ? {} : { unit })}
          {...(changed === undefined ? {} : { changed })}
          format={args.format ?? { kind: 'text' }}
        />
      ))}
    </Stack>
  ),
};

export const Loading: Story = { args: { loading: true } };

/** A dense list: dots instead of badges, one line each; the state is read aloud. */
export const Dense: Story = {
  render: () => (
    <Stack gap={0}>
      {SAMPLES.map(({ tone, label, name, technicalName, value, unit, changed }) => (
        <IndicatorRow
          key={name}
          indicator="dot"
          status={{ tone, label }}
          name={name}
          technicalName={technicalName}
          value={value}
          {...(unit === undefined ? {} : { unit })}
          {...(changed === undefined ? {} : { changed })}
        >
          {DETAIL}
        </IndicatorRow>
      ))}
    </Stack>
  ),
};
