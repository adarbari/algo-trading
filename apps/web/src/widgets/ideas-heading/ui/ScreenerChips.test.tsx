import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { ScreenerSummary } from '@/entities/idea';
import { expectNoA11yViolations } from '@/shared/lib/testing';

import { ScreenerChips } from './ScreenerChips';

vi.mock('@/features/guide-help', async () => {
  const { Button } = await import('@algotrade/ui');
  return { termHelp: (id: string) => <Button>{`Help: ${id}`}</Button> };
});

const base: ScreenerSummary = {
  id: 'vrp',
  name: 'VRP scanner',
  owner: 'site',
  version: 1,
  picked: 14,
  notRun: null,
  withheld: false,
  coverage: 'COMPLETE',
  gaps: [],
  top: [],
};

const screeners: ScreenerSummary[] = [
  base,
  {
    ...base,
    id: 'liq',
    name: 'Liquidity',
    picked: 1,
    coverage: 'PARTIAL',
    gaps: [
      { kind: 'NOT_STORED', kindText: 'not stored for this session', guideTerm: 'not_stored' },
    ],
  },
  {
    ...base,
    id: 'gone',
    name: 'Gone',
    picked: 0,
    coverage: null,
    notRun: {
      code: 'NOT_RUN',
      kind: 'NOT_RUN',
      guideTerm: 'not_run',
      kindText: 'not run for this session',
      reason: null,
      cause: null,
    },
  },
];

describe('ScreenerChips', () => {
  it('shows each screener with its state and links to its page', async () => {
    const { container } = render(<ScreenerChips screeners={screeners} />);
    const items = screen.getAllByRole('listitem');
    expect(items).toHaveLength(3);
    expect(items[0]).toHaveTextContent('VRP scanner14 picks');
    expect(items[1]).toHaveTextContent('1 pick · partial');
    expect(items[1]).toHaveTextContent('not stored for this session');
    expect(items[2]).toHaveTextContent('Not run');
    expect(screen.getByRole('link', { name: 'VRP scanner' })).toHaveAttribute(
      'href',
      expect.stringContaining('vrp'),
    );
    await expectNoA11yViolations(container);
  });

  it('gives every state without a plain run its Guide help, and starts no run', () => {
    render(<ScreenerChips screeners={screeners} />);
    expect(screen.getByRole('button', { name: 'Help: partial_run' })).toBeVisible();
    expect(screen.getByRole('button', { name: 'Help: not_run' })).toBeVisible();
    expect(screen.queryByRole('button', { name: /run now/i })).toBeNull();
  });

  it('renders nothing without screeners', () => {
    const { container } = render(<ScreenerChips screeners={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
