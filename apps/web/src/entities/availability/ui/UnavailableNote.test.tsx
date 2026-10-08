import { Button } from '@algotrade/ui';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '@/shared/lib/testing';

import { TermHelpProvider } from '../model/help';
import type { ServedUnavailable } from '../model/served';
import { UnavailableNote } from './UnavailableNote';
import { UnknownNote } from './UnknownNote';

const CHAIN = {
  links: [
    { level: 'SOURCE', subject: 'IB Gateway', status: 'FAILED', message: 'unreachable' },
    { level: 'STEP', subject: 'ibkr-iv', status: 'FAILED', message: '' },
    { level: 'TABLE', subject: 'rollups/instrument/ibkr_iv@v1', status: 'MISSING', message: '' },
  ],
} as const;

const GAPS: ServedUnavailable[] = [
  {
    kind: 'SYSTEM',
    features: ['rollup.ibkr_iv@v1.iv_rank', 'rollup.ibkr_iv@v1.iv30'],
    guideTerm: 'unavailable_system',
    kindText: 'not available because of a system error',
    cause: null,
  },
  {
    kind: 'SYSTEM',
    features: ['rollup.ibkr_iv@v1.iv30', 'rollup.price_stats@v2.hv20'],
    guideTerm: 'unavailable_system',
    kindText: 'not available because of a system error',
    cause: null,
  },
  {
    kind: 'NOT_STORED',
    features: ['rollup.earnings@v1.next_earnings_date'],
    guideTerm: 'unavailable_not_stored',
    kindText: 'not available for this instrument',
    cause: null,
  },
];

describe('UnavailableNote', () => {
  it('shows a trader one note per kind with the features, and no table, source or step', async () => {
    const { container } = render(<UnavailableNote gaps={GAPS} />);
    expect(screen.getAllByText('Not available: system error')).toHaveLength(1);
    expect(screen.getByText('Not available for this instrument')).toBeVisible();
    expect(screen.queryByRole('list', { name: 'Cause chain' })).toBeNull();
    expect(container).not.toHaveTextContent(/rollups\/|IB Gateway|ibkr-iv/);
    await expectNoA11yViolations(container);
  });

  it('shows an admin the chain the server sent, one per gap, under its kind', async () => {
    const withCause = GAPS.map((gap, i) => (i < 2 ? { ...gap, cause: CHAIN } : gap));
    const { container } = render(<UnavailableNote gaps={withCause} />);
    expect(screen.getAllByRole('list', { name: 'Cause chain' })).toHaveLength(2);
    expect(screen.getAllByText('IB Gateway')).toHaveLength(2);
    expect(screen.getAllByText('ibkr-iv')).toHaveLength(2);
    await expectNoA11yViolations(container);
  });

  it("draws the app's help button for the kind's Guide term, when the app provides one", () => {
    render(
      <TermHelpProvider render={(id) => <Button>help {id}</Button>}>
        <UnavailableNote gaps={GAPS} />
      </TermHelpProvider>,
    );
    expect(screen.getByRole('button', { name: 'help unavailable_system' })).toBeVisible();
    expect(screen.getByRole('button', { name: 'help unavailable_not_stored' })).toBeVisible();
  });

  it('renders nothing for no gaps', () => {
    const { container } = render(<UnavailableNote gaps={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe('UnknownNote', () => {
  const unknown = {
    code: 'NO_PARTITION',
    kind: 'SYSTEM',
    guideTerm: 'unavailable_system',
    kindText: 'not available because of a system error',
  } as const;

  it("says the kind's generic words to a trader, with no chain", () => {
    const { container } = render(<UnknownNote unknown={{ ...unknown, cause: null }} />);
    expect(screen.getByText('not available because of a system error')).toBeVisible();
    expect(screen.queryByRole('list', { name: 'Cause chain' })).toBeNull();
    expect(container).not.toHaveTextContent(/rollups\//);
  });

  it('draws the chain an admin was sent under the same words', () => {
    render(<UnknownNote unknown={{ ...unknown, cause: CHAIN }} />);
    expect(screen.getByText('not available because of a system error')).toBeVisible();
    expect(screen.getByRole('list', { name: 'Cause chain' })).toBeVisible();
  });

  it('says what a stored null means when no failure stands behind it', () => {
    render(
      <UnknownNote
        unknown={{ ...unknown, code: 'NULL', kind: 'NOT_STORED', cause: null }}
        nullMeaning="no report date on or after the session"
      />,
    );
    expect(screen.getByText('no report date on or after the session')).toBeVisible();
  });
});
