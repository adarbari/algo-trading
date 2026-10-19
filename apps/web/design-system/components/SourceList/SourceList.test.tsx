import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { SourceList } from './SourceList';

const items = [
  {
    id: 's1',
    kind: 'Academic paper',
    title: 'A (2001)',
    url: 'https://example.org/a',
    why: 'Why.',
  },
  { id: 's2', kind: 'Filing', title: 'B (2002)', url: 'https://example.org/b' },
];

describe('SourceList', () => {
  it('is a numbered list: kind, link and why, each item anchored by its id', () => {
    const { container } = render(<SourceList aria-label="Sources" items={items} />);
    expect(screen.getByRole('list').tagName).toBe('OL');
    expect(screen.getAllByRole('link')[0]).toHaveAttribute('href', 'https://example.org/a');
    expect(screen.getByText('Academic paper')).toBeInTheDocument();
    expect(screen.getByText('Why.')).toBeInTheDocument();
    expect(container.querySelector('#s2')).not.toBeNull();
  });

  it('leaves the kind line out when an item has none', () => {
    render(
      <SourceList
        aria-label="Sources"
        items={[{ id: 's1', title: 'C (2003)', url: 'https://example.org/c' }]}
      />,
    );
    expect(screen.getByRole('link', { name: /C \(2003\)/ })).toBeInTheDocument();
    expect(screen.queryByText('Academic paper')).toBeNull();
  });

  it('shows the title as plain text when a source has no page', () => {
    render(
      <SourceList aria-label="Sources" items={[{ id: 's1', title: 'Street Smarts (1995)' }]} />,
    );
    expect(screen.getByText('Street Smarts (1995)')).toBeInTheDocument();
    expect(screen.queryByRole('link')).toBeNull();
  });

  it('renders nothing without items', () => {
    const { container } = render(<SourceList aria-label="Sources" items={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<SourceList aria-label="Sources" items={items} />);
    await expectNoA11yViolations(container);
  });
});
