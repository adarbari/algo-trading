import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { DataStatusView } from '@/entities/system-status';
import { expectNoA11yViolations } from '@/shared/lib/testing';

import { DataStatusPill, pillText } from './DataStatusPill';

const hooks = vi.hoisted(() => ({ useDataStatus: vi.fn() }));
vi.mock('@/entities/system-status', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useDataStatus: hooks.useDataStatus,
}));
vi.mock('@/features/guide-help', () => ({
  GuideHelp: ({ entry }: { entry: { id: string } }) => `help ${entry.id}`,
  guidePath: (entry: { id: string }) => `/guide/terms/${entry.id}`,
}));

const BASE: DataStatusView = {
  date: '2026-10-22',
  newerDate: null,
  state: 'COMPLETE',
  knowledgeTs: '2026-10-22T21:05:00+00:00',
  datasets: [
    { name: 'PRICES', status: 'COMPLETE', share: 0.99, gap: null, gaps: [] },
    { name: 'OPTIONS_CHAINS', status: 'PARTIAL', share: 0.62, gap: null, gaps: [] },
    {
      name: 'FUNDAMENTALS',
      status: 'UNKNOWN',
      share: null,
      gap: 'Not available yet',
      gaps: [
        {
          kindText: 'Not available yet',
          cause: {
            links: [{ level: 'STEP', subject: 'sec-facts', status: 'FAILED', message: 'timeout' }],
          },
        },
      ],
    },
  ],
  affectedScreeners: 2,
  totalScreeners: 7,
};

const STATES: Array<[DataStatusView['state'], string, string | null]> = [
  ['COMPLETE', 'Data: 22 Oct, complete', null],
  ['PARTIAL', 'Data: 22 Oct, partial', null],
  ['NEXT_PROCESSING', '23 Oct is processing', '2026-10-23'],
  ['NEXT_FAILED_SHOWING_PREVIOUS', '23 Oct failed, showing 22 Oct', '2026-10-23'],
];

/** What the server sends a trader: the same gaps without a cause chain. */
const TRADER: DataStatusView = {
  ...BASE,
  datasets: BASE.datasets.map((d) => ({
    ...d,
    gaps: d.gaps.map(({ cause: _cause, ...gap }) => gap),
  })),
};

beforeEach(() => hooks.useDataStatus.mockReset());

describe('DataStatusPill', () => {
  it.each(STATES)('says %s in the server-given words and dates', (state, text, newerDate) => {
    hooks.useDataStatus.mockReturnValue({ ...BASE, state, newerDate });
    render(<DataStatusPill admin={false} />);
    expect(screen.getByRole('button', { name: text })).toBeInTheDocument();
    expect(pillText({ ...BASE, state, newerDate })).toBe(text);
  });

  it('shows nothing without data', () => {
    hooks.useDataStatus.mockReturnValue(null);
    const { container } = render(<DataStatusPill admin={false} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('opens the detail for a trader: session, datasets with the server share, counts, no cause', async () => {
    hooks.useDataStatus.mockReturnValue(TRADER);
    render(<DataStatusPill admin={false} />);
    await userEvent.click(screen.getByRole('button', { name: 'Data: 22 Oct, complete' }));
    expect(
      await screen.findByText(/Session 22 Oct 2026 · known from 2026-10-22 21:05 UTC/),
    ).toBeVisible();
    expect(screen.getByText('Prices')).toBeInTheDocument();
    expect(screen.getByText('Options chains')).toBeInTheDocument();
    expect(screen.getByText('99% of names')).toBeInTheDocument();
    expect(screen.getByText('62% of names')).toBeInTheDocument();
    expect(screen.getByText('Not available yet')).toBeInTheDocument();
    expect(screen.getByText('Affects 2 of your 7 screeners')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Guide' })).toHaveAttribute(
      'href',
      '/guide/terms/data_state',
    );
    expect(screen.queryByRole('link', { name: 'Ingestion' })).not.toBeInTheDocument();
    expect(screen.queryByText('sec-facts')).not.toBeInTheDocument();
    await expectNoA11yViolations(document.body);
  });

  it('adds the cause and the ingestion link for an admin', async () => {
    hooks.useDataStatus.mockReturnValue(BASE);
    render(<DataStatusPill admin />);
    expect(hooks.useDataStatus).toHaveBeenCalledWith(true);
    await userEvent.click(screen.getByRole('button', { name: 'Data: 22 Oct, complete' }));
    expect(await screen.findByText('sec-facts')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Ingestion' })).toHaveAttribute(
      'href',
      '/admin/ingestion',
    );
  });
});
