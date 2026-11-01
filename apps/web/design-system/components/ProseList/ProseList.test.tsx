import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { ProseList } from './ProseList';

const items = [
  { id: 'a', lead: 'First.', body: 'One.' },
  { id: 'b', body: 'Two.' },
];

describe('ProseList', () => {
  it('is a bulleted list with the lead-in before the body', () => {
    render(<ProseList items={items} />);
    expect(screen.getAllByRole('listitem')).toHaveLength(2);
    expect(screen.getByRole('list').tagName).toBe('UL');
    expect(screen.getAllByRole('listitem')[0]).toHaveTextContent('First. One.');
  });

  it('is a numbered list when ordered', () => {
    render(<ProseList items={items} ordered />);
    expect(screen.getByRole('list').tagName).toBe('OL');
  });

  it('marks a checklist', () => {
    render(<ProseList items={items} marker="box" />);
    expect(screen.getByRole('list')).toHaveAttribute('data-marker', 'box');
  });

  it('renders nothing without items', () => {
    const { container } = render(<ProseList items={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<ProseList items={items} aria-label="Why it survives" />);
    await expectNoA11yViolations(container);
  });
});
