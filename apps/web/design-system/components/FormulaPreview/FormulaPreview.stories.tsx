import type { Meta, StoryObj } from '@storybook/react-vite';

import { narrow } from '../../testing';
import { Button } from '../Button';
import { FormulaPreview, type FormulaSample } from './FormulaPreview';

const sample: FormulaSample = {
  label: 'Sample rows',
  labelHeader: 'Symbol',
  columns: [
    { id: 'close', header: 'close' },
    { id: 'high', header: 'high_52w' },
    { id: 'value', header: 'value', format: { kind: 'number', digits: 3 } },
  ],
  rows: [
    { id: 'JPM', label: 'JPM', values: { close: 241.0, high: 246.5, value: -0.022 } },
    { id: 'AAPL', label: 'AAPL', values: { close: 226.1, high: 237.2, value: -0.047 } },
    { id: 'XOM', label: 'XOM', values: { close: 118.2, high: 126.3, value: -0.064 } },
    { id: 'MSFT', label: 'MSFT', values: { close: 431.5, high: 468.35, value: -0.079 } },
  ],
};

const meta = {
  title: 'Components/FormulaPreview',
  component: FormulaPreview,
  args: {
    name: 'draft_near_52w_high',
    formula: 'close / price_stats.high_52w - 1',
    inputs: 'Inputs: close, price_stats.high_52w · a ratio, 0 is at the high',
    statsLabel: 'Dry run',
    stats: [
      { label: 'Rows checked', value: 13334, format: { kind: 'number', digits: 0 } },
      { label: 'No value', value: 0.062, format: { kind: 'percent', digits: 1 } },
      { label: 'Range', value: '-0.97 to 0' },
      { label: 'Passing', value: 612, format: { kind: 'number', digits: 0 } },
    ],
    sample,
    actions: (
      <>
        <Button variant="primary">Review and add</Button>
        <Button variant="ghost">Skip</Button>
      </>
    ),
  },
  parameters: {
    states: {
      notApplicable: {
        Loading:
          'a preview exists only once the dry run has finished; the review panel shows the waiting phase',
        Empty:
          'a draft formula is always shown; with no sample rows the table is left out (story NoSample)',
        Error: 'a failed dry run is the review panel’s error state',
        Dense: 'a single preview, not a list',
      },
    },
  },
} satisfies Meta<typeof FormulaPreview>;

export default meta;
type Story = StoryObj<typeof meta>;

/** The Describe it example: draft_near_52w_high over 13,334 rows. */
export const Default: Story = {};

/** No sample rows (the dry run found none to show). */
export const NoSample: Story = { args: { sample: undefined, actions: undefined } };

/** A phone: the stats go two by two, the formula wraps. */
export const Narrow: Story = { decorators: [narrow] };
