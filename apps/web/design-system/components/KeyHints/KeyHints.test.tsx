import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { KeyHints } from './KeyHints';

const HINTS = [
  { keys: ['j', 'k'], label: 'move' },
  { keys: ['Enter'], label: 'open' },
];

describe('KeyHints', () => {
  it('lists each hint with its keys outlined and its meaning', () => {
    render(<KeyHints hints={HINTS} />);
    const list = screen.getByRole('list', { name: 'Keyboard shortcuts' });
    const items = screen.getAllByRole('listitem');
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent('jkmove');
    expect(items[0]?.querySelectorAll('kbd kbd')).toHaveLength(2);
    expect(list).toBeInTheDocument();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<KeyHints hints={HINTS} label="Shortcuts" />);
    await expectNoA11yViolations(container);
  });
});
