import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { Kbd } from './Kbd';

describe('Kbd', () => {
  it('renders each key of a chord as a nested kbd joined by +', () => {
    const { container } = render(<Kbd keys={['Ctrl', 'K']} />);
    const outer = container.firstElementChild;
    expect(outer?.tagName).toBe('KBD');
    expect(outer).toHaveTextContent('Ctrl+K');
    expect(outer?.querySelectorAll('kbd')).toHaveLength(2);
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<Kbd keys={['/']} />);
    await expectNoA11yViolations(container);
  });
});
