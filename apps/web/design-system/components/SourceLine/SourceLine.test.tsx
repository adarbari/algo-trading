import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { SourceLine } from './SourceLine';

const A = { label: 'Chicago Fed NFCI', cadence: 'weekly', url: 'https://example.org/nfci' };
const B = { label: 'FRED T10Y3M', url: 'https://example.org/t10y3m' };

describe('SourceLine', () => {
  it('reads "Source:", a link per source and the cadence after a dot', () => {
    const { container } = render(<SourceLine sources={[A]} />);
    expect(screen.getByText('Source:')).toBeInTheDocument();
    expect(screen.getByRole('link')).toHaveAttribute('href', A.url);
    expect(screen.getByText('· weekly')).toBeInTheDocument();
    expect(container.textContent).toContain('Chicago Fed NFCI');
  });

  it('says "Sources:" for several and writes no dot for a missing cadence', () => {
    render(<SourceLine sources={[A, B]} />);
    expect(screen.getByText('Sources:')).toBeInTheDocument();
    expect(screen.getAllByRole('link')).toHaveLength(2);
    expect(screen.getAllByText(/^·/)).toHaveLength(1);
  });

  it('renders nothing without sources', () => {
    const { container } = render(<SourceLine sources={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<SourceLine sources={[A, B]} />);
    await expectNoA11yViolations(container);
  });
});
