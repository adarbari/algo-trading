import type { Meta, StoryObj } from '@storybook/react-vite';

import { narrow } from '../../testing';
import { SourceList } from './SourceList';

const meta = {
  title: 'Components/SourceList',
  component: SourceList,
  args: {
    'aria-label': 'Sources and further reading',
    items: [
      {
        id: 's1',
        kind: 'Academic paper',
        title:
          'Bernard and Thomas (1989), Post-Earnings-Announcement Drift: Delayed Price Response or Risk Premium?, Journal of Accounting Research',
        url: 'https://doi.org/10.2307/2491062',
        why: 'The paper that named the drift.',
      },
      {
        id: 's2',
        kind: 'Regulator filing',
        title: 'SEC Form 8-K, Items 2.02 and 5.02',
        url: 'https://www.sec.gov/files/form8-k.pdf',
      },
    ],
  },
  parameters: {
    states: {
      notApplicable: {
        Loading: 'a bibliography is static page content',
        Empty: 'no sources renders nothing; the section is left out',
        Error: 'a source list holds no data of its own',
      },
    },
  },
} satisfies Meta<typeof SourceList>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

/** Many sources; a long title wraps. */
export const Dense: Story = {
  args: {
    items: Array.from({ length: 8 }, (_, i) => ({
      id: `s${i + 1}`,
      kind: 'Academic paper',
      title: `Author and Author (20${10 + i}), A long paper title that wraps onto several lines, Journal`,
      url: `https://example.org/paper-${i + 1}`,
      why: 'Why it is worth reading.',
    })),
  },
};

export const Narrow: Story = { ...Dense, decorators: [narrow] };
