/**
 * NavTabs: a workspace's section links in the top bar (Ideas, Screeners, Explore, ...), the
 * current one marked with `aria-current="page"` and the accent tint. Router-agnostic: links go
 * through the app's `LinkProvider` (plain anchors without one), or `renderLink` renders the
 * router link with the given props (the design system never imports the router). One row that scrolls sideways when the sections do
 * not fit, the current link scrolled into view. `variant="steps"` numbers the links as the steps
 * of a flow (the Test flow: Start, Build, Result); the number is a CSS counter, the label stays
 * the link's name. For switching views inside a page use Tabs.
 */
import { Fragment, useEffect, useRef, type ReactNode } from 'react';

import { useRenderLink } from '../TextLink';
import styles from './NavTabs.module.css';

export interface NavItem {
  /** The destination (a path such as "/ideas"). */
  href: string;
  label: string;
}

/** What `renderLink` receives: spread it onto the router's link (map `href` to its prop). */
export interface NavLinkRenderProps {
  href: string;
  className: string;
  'aria-current': 'page' | undefined;
  'data-active': true | undefined;
  children: ReactNode;
}

export interface NavTabsProps {
  /** The sections, in order. */
  items: readonly NavItem[];
  /** The `href` of the current section. */
  activeHref?: string;
  /** The navigation landmark's name ("Trader sections"). */
  'aria-label': string;
  /** Renders one link (e.g. the router's Link); default: the app's `LinkProvider` link, else a plain anchor. */
  renderLink?: (link: NavLinkRenderProps) => ReactNode;
  /** `bar` (default): section links; `steps`: the links numbered as the steps of a flow. */
  variant?: 'bar' | 'steps';
}

export function NavTabs({
  items,
  activeHref,
  'aria-label': ariaLabel,
  renderLink,
  variant = 'bar',
}: NavTabsProps) {
  const contextLink = useRenderLink();
  const render = renderLink ?? contextLink;
  const navRef = useRef<HTMLElement>(null);
  // Keep the current section visible in the scrolling row (jsdom has no scrollIntoView).
  useEffect(() => {
    const active = navRef.current?.querySelector<HTMLElement>('[aria-current="page"]');
    // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition -- absent in jsdom
    active?.scrollIntoView?.({ inline: 'nearest', block: 'nearest' });
  }, [activeHref]);
  return (
    <nav ref={navRef} aria-label={ariaLabel} className={styles.nav} data-variant={variant}>
      {items.map((item) => {
        const active = item.href === activeHref;
        return (
          <Fragment key={item.href}>
            {render({
              href: item.href,
              className: styles.link ?? '',
              'aria-current': active ? 'page' : undefined,
              'data-active': active || undefined,
              children: item.label,
            })}
          </Fragment>
        );
      })}
    </nav>
  );
}
