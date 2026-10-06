import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { ExternalLink } from './ExternalLink';

describe('ExternalLink', () => {
  it('is a link that opens a new tab without leaking the opener', () => {
    render(
      <ExternalLink href="https://fred.stlouisfed.org/series/NFCI">Chicago Fed NFCI</ExternalLink>,
    );
    const link = screen.getByRole('link', { name: 'Chicago Fed NFCI, opens in a new tab' });
    expect(link).toHaveAttribute('href', 'https://fred.stlouisfed.org/series/NFCI');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('exposes the size as a styling hook', () => {
    render(
      <ExternalLink href="https://example.org/" size="sm">
        Sahm rule
      </ExternalLink>,
    );
    expect(screen.getByRole('link')).toHaveAttribute('data-size', 'sm');
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <ExternalLink href="https://example.org/">An explainer</ExternalLink>,
    );
    await expectNoA11yViolations(container);
  });
});
