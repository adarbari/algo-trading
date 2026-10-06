import type { Meta, StoryObj } from '@storybook/react-vite';

import { Stack } from '../../primitives/Stack';
import { ScoreMeter, type ScoreThreshold } from './ScoreMeter';

/** Two bands above the base: caution from 50, stress from 75. Sample values. */
const BANDS: ScoreThreshold[] = [
  { at: 50, label: 'caution', tone: 'warning' },
  { at: 75, label: 'stress', tone: 'negative' },
];

const meta = {
  title: 'Components/ScoreMeter',
  component: ScoreMeter,
  args: {
    value: 62,
    label: 'Slow-warning score',
    thresholds: BANDS,
    baseTone: 'positive',
    baseLabel: 'calm',
    caption: 'Up from 48 last month.',
  },
  parameters: {
    states: {
      notApplicable: {
        Error: 'a meter draws a number it is given; the panel around it shows a failed load',
      },
    },
  },
} satisfies Meta<typeof ScoreMeter>;

export default meta;
type Story = StoryObj<typeof meta>;

/** In the caution band: amber fill, the marker at 62, the band named beside the value. */
export const Default: Story = {};

/** The value in each band (and below the first): the tone follows the band, never the caller. */
export const Bands: Story = {
  render: ({ caption: _caption, ...rest }) => (
    <Stack gap={3}>
      <ScoreMeter {...rest} value={18} label="Calm" />
      <ScoreMeter {...rest} value={62} label="Caution" />
      <ScoreMeter {...rest} value={88} label="Stress" />
    </Stack>
  ),
};

/** No thresholds: a plain meter in the base tone, on a 0-10 scale. */
export const Plain: Story = {
  args: { value: 7.5, min: 0, max: 10, thresholds: [], baseTone: 'accent', caption: 'Out of 10.' },
};

/** A headline meter: thicker track, ticks near both ends keep their labels inside. */
export const Headline: Story = {
  args: {
    size: 'md',
    value: 81,
    thresholds: [
      { at: 10, label: 'low', tone: 'neutral' },
      { at: 50, label: 'caution', tone: 'warning' },
      { at: 90, label: 'crisis', tone: 'negative' },
    ],
  },
};

export const Loading: Story = { args: { loading: true } };

/** Unknown score: a dashed empty track and the reason, never a zero. */
export const Empty: Story = {
  args: { value: null, unknownReason: 'No macro data for 2 Oct' },
};

export const Dense: Story = {
  render: ({ caption: _caption, ...rest }) => (
    <Stack gap={2}>
      {[
        ['Slow signs', 62],
        ['Fast signs', 12],
        ['Credit', 81],
        ['Breadth', 44],
      ].map(([label, value]) => (
        <ScoreMeter key={label} {...rest} label={String(label)} value={Number(value)} />
      ))}
    </Stack>
  ),
};
