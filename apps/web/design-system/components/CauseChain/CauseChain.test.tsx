import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { CauseChain, statusTone, type CauseLink } from './CauseChain';

const CHAIN: CauseLink[] = [
  { level: 'SOURCE', subject: 'ibkr', status: 'FAILED', message: 'IB Gateway unreachable' },
  { level: 'STEP', subject: 'ibkr-iv', status: 'FAILED' },
  { level: 'TABLE', subject: 'rollups/instrument/ibkr_iv@v1', message: 'no rows for the session' },
  { level: 'FEATURE', subject: 'iv_rank, iv_percentile' },
];

describe('CauseChain', () => {
  it('lists the links in order, root first', () => {
    render(<CauseChain links={CHAIN} />);
    const items = within(screen.getByRole('list', { name: 'Cause chain' })).getAllByRole(
      'listitem',
    );
    expect(items).toHaveLength(4);
    expect(items[0]).toHaveTextContent('ibkr');
    expect(items[3]).toHaveTextContent('iv_rank, iv_percentile');
  });

  it('shows a state badge and message only when given', () => {
    render(<CauseChain links={CHAIN} />);
    const badges = screen.getAllByText('FAILED');
    expect(badges).toHaveLength(2);
    expect(badges[0]).toHaveAttribute('data-tone', 'negative');
    expect(screen.getByText('IB Gateway unreachable')).toBeInTheDocument();
  });

  it('renders nothing for no links', () => {
    const { container } = render(<CauseChain links={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('tones a state by its meaning', () => {
    expect(statusTone('succeeded')).toBe('positive');
    expect(statusTone('FAILED')).toBe('negative');
    expect(statusTone('PARTIAL')).toBe('warning');
    expect(statusTone('PENDING')).toBe('neutral');
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<CauseChain links={CHAIN} />);
    await expectNoA11yViolations(container);
  });
});
