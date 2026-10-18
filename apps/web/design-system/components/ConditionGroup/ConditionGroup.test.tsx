import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { ConditionGroup, type ConditionGroupProps } from './ConditionGroup';

const base: Omit<ConditionGroupProps, 'children'> = {
  kind: 'any',
  kindLabel: 'Any of',
  title: 'Either setup',
  connectorLabel: 'or',
  joinedByLabel: 'joined by',
};

describe('ConditionGroup', () => {
  it('is a section named by its heading, with a connector between members only', async () => {
    const { container } = render(
      <ConditionGroup {...base} actions={<button type="button">Ungroup</button>}>
        <p>first</p>
        <p>second</p>
        <p>third</p>
      </ConditionGroup>,
    );
    expect(screen.getByRole('region', { name: 'Either setup' })).toBeInTheDocument();
    expect(screen.getByText('Any of')).toBeInTheDocument();
    expect(screen.getAllByRole('listitem')).toHaveLength(3);
    expect(screen.getAllByText('or')).toHaveLength(2);
    expect(screen.getByRole('button', { name: 'Ungroup' })).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it('joins none-of members with the not connector', () => {
    render(
      <ConditionGroup {...base} kind="none" kindLabel="None of" connectorLabel="and not">
        <p>a</p>
        <p>b</p>
      </ConditionGroup>,
    );
    expect(screen.getByText('and not')).toBeInTheDocument();
  });

  it('read only is one row that shows its members on expanding', async () => {
    const { container } = render(
      <ConditionGroup {...base} readOnly expression="price above 5 or volume above 1M">
        <p>first</p>
        <p>second</p>
      </ConditionGroup>,
    );
    const button = screen.getByRole('button', { name: /price above 5 or volume above 1M/ });
    expect(button).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText('first')).toBeNull();
    expect(screen.queryByRole('heading')).toBeNull();
    await userEvent.setup().click(button);
    expect(screen.getByText('first')).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });
});
