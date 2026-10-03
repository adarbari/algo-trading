/**
 * NavTabs: a workspace's section links in the top bar (Ideas, Screeners, Explore, ...), the
 * current one marked with `aria-current="page"` and the accent tint. Router-agnostic: links are
 * plain anchors unless `renderLink` renders the app's router link with the given props (the
 * design system never imports the router). For switching views inside a page use Tabs.
 */
import type { ReactNode } from 'react';

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
  /** Renders one link (e.g. the router's Link); a plain anchor by default. */
  renderLink?: (link: NavLinkRenderProps) => ReactNode;
}

const anchor = ({ children, ...props }: NavLinkRenderProps) => <a {...props}>{children}</a>;

export function NavTabs({
  items,
  activeHref,
  'aria-label': ariaLabel,
  renderLink = anchor,
}: NavTabsProps) {
  return (
    <nav aria-label={ariaLabel} className={styles.nav}>
      {items.map((item) => {
        const active = item.href === activeHref;
        return (
          <span key={item.href} className={styles.item}>
            {renderLink({
              href: item.href,
              className: styles.link ?? '',
              'aria-current': active ? 'page' : undefined,
              'data-active': active || undefined,
              children: item.label,
            })}
          </span>
        );
      })}
    </nav>
  );
}
