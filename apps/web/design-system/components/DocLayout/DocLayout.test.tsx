import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { DocLayout, DocSection } from './DocLayout';

describe('DocLayout', () => {
  it('holds the rail, the article and the aside in reading order', () => {
    render(
      <DocLayout rail={<span>rail</span>} aside={<span>aside</span>}>
        <DocSection id="reads">body</DocSection>
      </DocLayout>,
    );
    expect(document.body).toHaveTextContent(/^railbodyaside$/);
    expect(screen.getByRole('article')).toBeInTheDocument();
  });

  it('gives a section its anchor', () => {
    render(
      <DocLayout>
        <DocSection id="use">body</DocSection>
      </DocLayout>,
    );
    expect(screen.getByText('body')).toHaveAttribute('id', 'use');
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <DocLayout rail={<span>rail</span>}>
        <DocSection id="a">body</DocSection>
      </DocLayout>,
    );
    await expectNoA11yViolations(container);
  });
});
