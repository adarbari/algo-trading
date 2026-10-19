import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { gql, TestQueryProvider } from '@/shared/api';
import { edgeEntry, expectNoA11yViolations, mechanism } from '@/shared/lib/testing';

import { GuideHelpProvider } from '../model/navigation';
import { GuideHelp } from './GuideHelp';

vi.mock('@/shared/api', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  gql: vi.fn(),
}));

const GQL = vi.mocked(gql);

function setup(entry: { kind: 'mechanism' | 'edge'; id: string }, navigate = vi.fn()) {
  const view = render(
    <TestQueryProvider>
      <GuideHelpProvider navigate={navigate}>
        <GuideHelp entry={entry} />
      </GuideHelpProvider>
    </TestQueryProvider>,
  );
  return { ...view, navigate };
}

beforeEach(() => {
  GQL.mockReset();
  GQL.mockResolvedValue({ guideMechanism: mechanism(), guideEdge: edgeEntry() });
});

describe('GuideHelp for a mechanism', () => {
  it('opens its question, hero, how it works and why it survives, and the full page', async () => {
    const { container, navigate } = setup({ kind: 'mechanism', id: 'slow_to_update' });
    await userEvent.click(await screen.findByRole('button', { name: 'About Slow to update' }));
    const drawer = await screen.findByRole('dialog');
    expect(await within(drawer).findByText(/A company reports and the price moves/)).toBeVisible();
    expect(within(drawer).getByText('Arbitrage is expensive to run.')).toBeVisible();
    expect(within(drawer).queryByText('The behaviour is old.')).toBeNull();
    expect(drawer).toHaveAccessibleDescription(/Who is slow to update/);
    await expectNoA11yViolations(container);
    expect(GQL.mock.calls[0]?.[1]).toEqual({ id: 'slow_to_update' });
    await userEvent.click(within(drawer).getByRole('button', { name: /Open full page/ }));
    expect(navigate).toHaveBeenCalledWith('/guide/edges/m/slow_to_update');
  });

  it('says so when the Guide has no such mechanism', async () => {
    GQL.mockResolvedValue({ guideMechanism: null });
    setup({ kind: 'mechanism', id: 'nope' });
    await userEvent.click(await screen.findByRole('button', { name: /^About / }));
    expect(await screen.findByText('The Guide has no entry for this mechanism yet.')).toBeVisible();
  });
});

describe('GuideHelp for an edge', () => {
  it('opens its thesis, status, the other side and why it lasts, and the full page', async () => {
    const { navigate } = setup({ kind: 'edge', id: 'earnings_date_advance' });
    await userEvent.click(
      await screen.findByRole('button', { name: 'About Earnings-date advances' }),
    );
    const drawer = await screen.findByRole('dialog');
    expect(
      await within(drawer).findByText(/read the date notice as a calendar item/),
    ).toBeVisible();
    expect(within(drawer).getByText(/a few weeks of life each quarter/)).toBeVisible();
    expect(drawer).toHaveAccessibleDescription(/Candidate/);
    expect(GQL.mock.calls[0]?.[1]).toEqual({ id: 'earnings_date_advance' });
    await userEvent.click(within(drawer).getByRole('button', { name: /Open full page/ }));
    expect(navigate).toHaveBeenCalledWith('/guide/edges/earnings_date_advance');
  });
});
