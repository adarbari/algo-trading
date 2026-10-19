import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { Text } from '@algotrade/ui';

import { edgeEntry, expectNoA11yViolations, fakeQuery } from '@/shared/lib/testing';

import { EdgeOutline, GuideEdge } from './GuideEdge';

const hooks = vi.hoisted(() => ({ useGuideEdge: vi.fn() }));

vi.mock('@/entities/guide', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useGuideEdge: hooks.useGuideEdge,
  RelatedTerms: ({ ids }: { ids: string[] }) => <Text>{`related ${ids.join(' ')}`}</Text>,
}));
vi.mock('@/features/guide-help', async () => {
  const { Text } = await import('@algotrade/ui');
  return { termHelp: (id: string) => <Text>{`help ${id}`}</Text> };
});

const setup = (onSeeEvidence = vi.fn()) => ({
  ...render(<GuideEdge id="earnings_date_advance" onSeeEvidence={onSeeEvidence} />),
  onSeeEvidence,
});

beforeEach(() => {
  hooks.useGuideEdge.mockReturnValue(fakeQuery(edgeEntry()));
});

describe('GuideEdge', () => {
  it('heads the page with the name, thesis and pills, and opens the live evidence', async () => {
    const { onSeeEvidence } = setup();
    expect(
      screen.getByRole('heading', { level: 1, name: 'Earnings-date advances' }),
    ).toBeInTheDocument();
    expect(screen.getByText(/next earnings date moves a week earlier/)).toBeInTheDocument();
    expect(screen.getAllByText('Candidate').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Stocks').length).toBeGreaterThan(0);
    expect(screen.getAllByText('20 sessions').length).toBeGreaterThan(0);
    expect(screen.getByRole('link', { name: 'Slow to update' })).toHaveAttribute(
      'href',
      '/guide/edges/m/slow_to_update',
    );
    await userEvent.click(screen.getByRole('button', { name: 'See the live evidence' }));
    expect(onSeeEvidence).toHaveBeenCalledOnce();
  });

  it('has the sections in the fixed order of the page', () => {
    setup();
    const headings = screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent);
    expect(headings).toEqual([
      'Who is on the other side',
      'Why it lasts',
      'What the research found',
      'How we test it',
      'How it is built',
      'What fools it',
      'Can you trade it',
      'Sources and further reading',
      'Related',
    ]);
  });

  it('shows the published figure with the planning haircut, and the paper it comes from', () => {
    setup();
    const research = screen.getByRole('region', { name: 'What the research found' });
    expect(within(research).getByText('2.6%')).toBeInTheDocument();
    expect(within(research).getByText('After our planning haircut')).toBeInTheDocument();
    expect(within(research).getByText('0.4 to 0.6%')).toBeInTheDocument();
    expect(screen.getByText('Johnson and So (2018) · 25 years')).toBeInTheDocument();
    expect(screen.getByText('help published_haircut')).toBeInTheDocument();
  });

  it('leaves the research section out when the document has no published figure', () => {
    hooks.useGuideEdge.mockReturnValue(fakeQuery(edgeEntry({ research: null })));
    setup();
    expect(screen.queryByText('What the research found')).toBeNull();
  });

  it('lists how it is tested, a glossary button only where the server names a term', () => {
    setup();
    const tested = screen.getByLabelText('How we test it');
    expect(within(tested).getByText('Excess return over SPY')).toBeInTheDocument();
    expect(within(tested).getByText('help excess_return')).toBeInTheDocument();
    expect(within(tested).getAllByText(/^help /)).toHaveLength(1);
  });

  it('links its screeners and the fields they read', () => {
    setup();
    expect(
      screen.getByRole('link', { name: 'Earnings date moved earlier · Events' }),
    ).toHaveAttribute('href', '/guide/screeners/earnings_date_shift');
    expect(screen.getByRole('link', { name: 'feature.days_since_date_shift' })).toHaveAttribute(
      'href',
      '/guide/fields/feature.days_since_date_shift',
    );
  });

  it('shows why a rejected edge is set aside', () => {
    hooks.useGuideEdge.mockReturnValue(
      fakeQuery(
        edgeEntry({
          summary: { ...edgeEntry().summary, status: 'rejected' },
          rejection: { segments: [{ text: 'Rejected: no lift over the base rate.', field: null }] },
        }),
      ),
    );
    setup();
    expect(screen.getByRole('alert')).toHaveTextContent('no lift over the base rate');
    expect(screen.getByText('Rejected')).toBeInTheDocument();
  });

  it('lists the sources, one without a link as plain text, and the related edges and terms', () => {
    setup();
    const sources = screen.getByRole('list', { name: 'Sources and further reading' });
    expect(within(sources).getByRole('link', { name: /Time Will Tell/ })).toHaveAttribute(
      'href',
      'https://example.org/js',
    );
    expect(screen.getByText('Source: A vendor note')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Momentum at earnings' })).toBeInTheDocument();
    expect(screen.getByText('related base_rate')).toBeInTheDocument();
  });

  it('lists its sections in "On this page"', () => {
    render(<EdgeOutline />);
    expect(
      within(screen.getByRole('navigation', { name: 'On this page' })).getByRole('link', {
        name: 'How we test it',
      }),
    ).toHaveAttribute('href', '#tested');
  });

  it('shows loading, an error with a retry, and an unknown edge', async () => {
    hooks.useGuideEdge.mockReturnValue(fakeQuery(undefined));
    const { rerender } = setup();
    expect(screen.getByRole('status')).toBeInTheDocument();
    const failed = fakeQuery(undefined, { isError: true });
    hooks.useGuideEdge.mockReturnValue(failed);
    rerender(<GuideEdge id="x" onSeeEvidence={vi.fn()} />);
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(failed.refetch).toHaveBeenCalled();
    hooks.useGuideEdge.mockReturnValue(fakeQuery(null));
    rerender(<GuideEdge id="nope" onSeeEvidence={vi.fn()} />);
    expect(screen.getByText('No such edge')).toBeInTheDocument();
  });

  it('has no accessibility violations', async () => {
    const { container } = setup();
    await expectNoA11yViolations(container);
  });
});
