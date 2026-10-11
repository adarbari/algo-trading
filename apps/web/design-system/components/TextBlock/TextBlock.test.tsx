import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { TextBlock } from './TextBlock';

describe('TextBlock', () => {
  it('shows the text as given under its name and can be focused to scroll', () => {
    render(<TextBlock label="Raw model answer" text={'Sure!\n  indented'} />);
    const block = screen.getByRole('region', { name: 'Raw model answer' });
    expect(block).toHaveTextContent('Sure! indented');
    expect(block.textContent).toBe('Sure!\n  indented');
    expect(block).toHaveAttribute('tabindex', '0');
  });

  it('says so when there is no text', () => {
    render(<TextBlock label="Raw model answer" text={null} empty="No answer kept" />);
    expect(screen.getByRole('region', { name: 'Raw model answer' })).toHaveTextContent(
      'No answer kept',
    );
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<TextBlock label="Error message" text="HTTP 529" size="sm" />);
    await expectNoA11yViolations(container);
  });
});
