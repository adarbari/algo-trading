import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { PartJoin } from './PartJoin';

describe('PartJoin', () => {
  it('shows the traders word and the logic, named in reading order', async () => {
    const { container } = render(
      <PartJoin join="and_not" label="AND NOT" words="except" joinedByLabel="joined by" />,
    );
    expect(screen.getByRole('group', { name: 'joined by except: AND NOT' })).toBeInTheDocument();
    expect(screen.getByText('except')).toBeInTheDocument();
    expect(screen.getByText('AND NOT')).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it('drops a word that only repeats the label, or no word at all', () => {
    const { rerender } = render(
      <PartJoin join="or" label="OR" words="or" joinedByLabel="joined by" />,
    );
    expect(screen.getAllByText(/^or$/i)).toHaveLength(1);
    rerender(<PartJoin join="and" label="AND" joinedByLabel="joined by" />);
    expect(screen.getByRole('group', { name: 'joined by AND' })).toBeInTheDocument();
  });

  it('tones OR and AND NOT apart from AND', () => {
    const { container, rerender } = render(
      <PartJoin join="and" label="AND" joinedByLabel="joined by" />,
    );
    expect(container.firstElementChild).toHaveAttribute('data-join', 'and');
    rerender(<PartJoin join="or" label="OR" joinedByLabel="joined by" />);
    expect(container.firstElementChild).toHaveAttribute('data-join', 'or');
  });
});
