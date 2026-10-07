import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { featureColumn, tickerColumn, type ColumnInfo, type TableRow } from '@/entities/feature';
import { gql, TestQueryProvider } from '@/shared/api';
import { expectNoA11yViolations, stubElementSize } from '@/shared/lib/testing';

import { TableFrame } from './TableFrame';

vi.mock('@/shared/api', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  gql: vi.fn(),
}));

stubElementSize();

const GQL = vi.mocked(gql);
const REL_VOLUME = 'rollup.momentum@v1.rel_volume';
const info = {
  name: REL_VOLUME,
  description: 'Volume over its average.',
  nullMeaning: 'Not enough history.',
  format: 'RATIO',
  unit: 'ratio',
  licence: 'open',
} as unknown as ColumnInfo;
const rows = [
  { symbol: 'AAPL', name: 'Apple', cells: { [REL_VOLUME]: { value: 1.4 } } },
] as unknown as TableRow[];

function setup() {
  return render(
    <TestQueryProvider>
      <TableFrame
        panel={{ title: 'Universe' }}
        summary="1 name"
        grid={{ columns: [tickerColumn(), featureColumn(info)], rows, label: 'Universe' }}
      />
    </TestQueryProvider>,
  );
}

beforeEach(() => {
  GQL.mockReset();
  GQL.mockResolvedValue({
    guideField: {
      info: {
        name: REL_VOLUME,
        unit: 'ratio',
        guide: {
          theme: 'volume',
          reads: 'Volume over average. More.',
          summary: 'Volume over average.',
          caveats: [],
          uses: [],
        },
      },
    },
  });
});

describe('TableFrame', () => {
  it('puts a help button in a field header and none in the ticker header', async () => {
    const { container } = setup();
    const field = await screen.findByRole('columnheader', { name: /Rel volume/i });
    expect(within(field).getByRole('button', { name: /What is .*\?/ })).toBeVisible();
    const ticker = screen.getByRole('columnheader', { name: /Ticker/ });
    expect(within(ticker).queryByRole('button', { name: /What is/ })).toBeNull();
    await expectNoA11yViolations(container);
  });

  it('opens the field drawer from the header without sorting the column', async () => {
    setup();
    const field = await screen.findByRole('columnheader', { name: /Rel volume/i });
    // The read arrives and the button gains its hover summary (a new element): click that one.
    await waitFor(() => {
      expect(within(field).getByRole('button', { name: /What is/ })).toHaveAttribute(
        'aria-describedby',
      );
    });
    await userEvent.click(within(field).getByRole('button', { name: /What is .*\?/ }));
    expect(await screen.findByRole('dialog')).toBeVisible();
    expect(screen.getByText('Volume over average. More.')).toBeVisible();
    expect(field).toHaveAttribute('aria-sort', 'none');
  });
});
