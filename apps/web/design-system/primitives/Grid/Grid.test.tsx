import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { breakpoint } from '../../tokens';
import { Grid } from './Grid';

describe('Grid', () => {
  it('renders a column count with a token gap', () => {
    render(
      <Grid aria-label="g" columns={3} gap={4}>
        x
      </Grid>,
    );
    const node = screen.getByLabelText('g');
    expect(node).toHaveAttribute('data-columns', '3');
    expect(node).toHaveAttribute('data-gap', '4');
    expect(node).not.toHaveAttribute('style');
  });

  it('wraps a collapsing grid in a size container', () => {
    render(
      <Grid aria-label="g" columns="main-aside" collapse="md">
        x
      </Grid>,
    );
    const node = screen.getByLabelText('g');
    expect(node).toHaveAttribute('data-collapse', 'md');
    expect(node.parentElement).toHaveClass('container');
  });

  it('uses the breakpoint tokens in its container queries', () => {
    const css = readFileSync(
      join(process.cwd(), 'design-system/primitives/Grid/Grid.module.css'),
      'utf8',
    );
    const found: Record<string, number> = {};
    for (const m of css.matchAll(
      /@container \(width < (\d+)px\) \{\s*\.grid\[data-collapse='(\w+)'\]/g,
    )) {
      found[m[2] ?? ''] = Number(m[1]);
    }
    expect(found).toEqual(breakpoint);
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <Grid as="ul" aria-label="Tickers" columns={2}>
        <li>AAPL</li>
        <li>MSFT</li>
      </Grid>,
    );
    await expectNoA11yViolations(container);
  });
});
