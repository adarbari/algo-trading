import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { NavTabs } from '../NavTabs';
import { TextLink } from '../TextLink';
import { TopBar } from './TopBar';

describe('TopBar', () => {
  it('is the banner landmark holding its slots in order', () => {
    render(
      <TopBar
        brand="algotrade"
        workspace={<span>switch</span>}
        nav={<NavTabs items={[{ href: '/a', label: 'A' }]} aria-label="Sections" />}
        end="As of Fri 2 Oct"
      />,
    );
    const banner = screen.getByRole('banner');
    expect(banner).toHaveTextContent(/^algotradeswitchAAs of Fri 2 Oct$/);
    expect(screen.getByRole('navigation', { name: 'Sections' })).toBeInTheDocument();
  });

  it('puts the utility slot after the nav and before the end slot', () => {
    render(
      <TopBar
        brand="algotrade"
        nav={<NavTabs items={[{ href: '/a', label: 'A' }]} aria-label="Sections" />}
        utility={
          <TextLink href="/guide" icon="book">
            Guide
          </TextLink>
        }
        end="Session"
      />,
    );
    expect(screen.getByRole('banner')).toHaveTextContent(/^algotradeAGuideSession$/);
    expect(screen.getByRole('link', { name: 'Guide' })).toHaveAttribute('href', '/guide');
  });

  it('renders the brand alone', () => {
    render(<TopBar brand="algotrade" />);
    expect(screen.getByRole('banner')).toHaveTextContent('algotrade');
  });

  it('wraps the nav in its own slot so a narrow bar can give it a row', () => {
    render(<TopBar brand="b" nav={<span>nav</span>} />);
    expect(screen.getByText('nav').parentElement).toHaveClass(/nav/);
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <TopBar
        brand="algotrade"
        nav={<NavTabs items={[{ href: '/a', label: 'A' }]} aria-label="Sections" />}
      />,
    );
    await expectNoA11yViolations(container);
  });
});
