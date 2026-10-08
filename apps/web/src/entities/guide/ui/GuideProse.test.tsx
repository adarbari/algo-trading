import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '@/shared/lib/testing';

import { GuideProse, proseParts } from './GuideProse';

const PROSE = {
  segments: [
    { text: 'Check ', field: null },
    { text: 'rollup.momentum@v1.rel_volume', field: 'rollup.momentum@v1.rel_volume' },
    { text: ' first.' },
  ],
};

describe('GuideProse', () => {
  it('turns a segment that names a field into a link to its Guide page, the rest into text', () => {
    expect(proseParts(PROSE)).toEqual([
      { text: 'Check ' },
      {
        text: 'rollup.momentum@v1.rel_volume',
        href: '/guide/fields/rollup.momentum%40v1.rel_volume',
      },
      { text: ' first.' },
    ]);
  });

  it('renders the words exactly as the server wrote them, the field names as links', () => {
    const { container } = render(<GuideProse prose={PROSE} />);
    expect(container.textContent).toBe('Check rollup.momentum@v1.rel_volume first.');
    expect(screen.getByRole('link')).toHaveAttribute(
      'href',
      '/guide/fields/rollup.momentum%40v1.rel_volume',
    );
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<GuideProse prose={PROSE} size="sm" tone="secondary" />);
    await expectNoA11yViolations(container);
  });
});
