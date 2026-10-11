import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { TaggedSentence } from './TaggedSentence';

const segments = [
  { text: 'Show', kind: 'plain' as const },
  { text: 'optionable stocks', kind: 'applied' as const, label: 'applied' },
  { text: 'near the high', kind: 'formula' as const, label: 'formula' },
  { text: 'liquid', kind: 'ask' as const, label: 'needs your call' },
  { text: 'with support', kind: 'gap' as const, label: 'not available yet' },
];

describe('TaggedSentence', () => {
  it('shows each tagged span with its kind and its text label', () => {
    render(<TaggedSentence segments={segments} aria-label="What was understood" />);
    expect(screen.getByText('optionable stocks')).toHaveAttribute('class');
    expect(screen.getByText('optionable stocks').parentElement).toHaveAttribute(
      'data-kind',
      'applied',
    );
    expect(screen.getByText('near the high').parentElement).toHaveAttribute('data-kind', 'formula');
    for (const label of ['applied', 'formula', 'needs your call', 'not available yet']) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  it('leaves plain words untagged and unlabelled', () => {
    render(<TaggedSentence segments={segments} />);
    expect(screen.getByText('Show').closest('[data-kind]')).toBeNull();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <TaggedSentence segments={segments} aria-label="What was understood" />,
    );
    await expectNoA11yViolations(container);
  });
});
