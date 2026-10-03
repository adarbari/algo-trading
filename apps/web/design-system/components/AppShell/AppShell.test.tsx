import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { TopBar } from '../TopBar';
import { AppShell } from './AppShell';

describe('AppShell', () => {
  it('lays out the banner above the main region', () => {
    render(
      <AppShell topBar={<TopBar brand="algotrade" />}>
        <h1>Ideas</h1>
      </AppShell>,
    );
    expect(screen.getByRole('banner')).toBeInTheDocument();
    expect(screen.getByRole('main')).toContainElement(screen.getByRole('heading', { level: 1 }));
    expect(screen.getByRole('main')).toHaveAttribute('data-layout', 'page');
  });

  it('offers a skip link to the main region as the first tab stop', async () => {
    render(
      <AppShell topBar={<TopBar brand="algotrade" />} layout="full">
        <p>Page</p>
      </AppShell>,
    );
    await userEvent.tab();
    const skip = screen.getByRole('link', { name: 'Skip to content' });
    expect(skip).toHaveFocus();
    expect(skip.getAttribute('href')).toBe(`#${screen.getByRole('main').id}`);
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <AppShell topBar={<TopBar brand="algotrade" />}>
        <h1>Ideas</h1>
      </AppShell>,
    );
    await expectNoA11yViolations(container);
  });
});
