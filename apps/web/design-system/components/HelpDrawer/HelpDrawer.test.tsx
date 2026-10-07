import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { InfoButton } from '../InfoButton';
import { HelpDrawer, HelpLead, HelpSection } from './HelpDrawer';

function Example() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <InfoButton
        label="What is rel_volume?"
        expanded={open}
        onClick={() => {
          setOpen(true);
        }}
      />
      <HelpDrawer
        open={open}
        onOpenChange={setOpen}
        eyebrow="rollup.momentum@v1.rel_volume"
        title="Relative volume"
        meta="Momentum and trend · ratio · nightly"
        fullPage={<a href="#full">Open full page</a>}
      >
        <HelpLead>The session’s volume over the average of the 20 sessions before it.</HelpLead>
        <HelpSection title="Use it for">
          <p>Heavy volume today</p>
        </HelpSection>
      </HelpDrawer>
    </>
  );
}

describe('HelpDrawer', () => {
  it('opens from the InfoButton with its header, sections and footer', async () => {
    render(<Example />);
    const user = userEvent.setup();
    const opener = screen.getByRole('button', { name: 'What is rel_volume?' });
    expect(opener).toHaveAttribute('aria-expanded', 'false');
    await user.click(opener);
    const drawer = screen.getByRole('dialog', { name: 'Relative volume' });
    expect(drawer).toHaveAttribute('data-side', 'end');
    expect(drawer).toHaveTextContent('rollup.momentum@v1.rel_volume');
    expect(drawer).toHaveAccessibleDescription('Momentum and trend · ratio · nightly');
    expect(screen.getByRole('heading', { level: 3, name: 'Use it for' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open full page' })).toBeInTheDocument();
    expect(opener).toHaveAttribute('aria-expanded', 'true');
  });

  it('closes on Escape and returns focus to the InfoButton', async () => {
    render(<Example />);
    const user = userEvent.setup();
    const opener = screen.getByRole('button', { name: 'What is rel_volume?' });
    await user.click(opener);
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(opener).toHaveFocus();
    expect(opener).toHaveAttribute('aria-expanded', 'false');
  });

  it('has no accessibility violations (open)', async () => {
    render(<Example />);
    await userEvent.click(screen.getByRole('button', { name: 'What is rel_volume?' }));
    await expectNoA11yViolations(document.body);
  });
});
