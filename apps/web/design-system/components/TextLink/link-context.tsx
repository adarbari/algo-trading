/**
 * The app's router link, offered to design-system links: `LinkProvider` (mounted once by the
 * app, which owns the router) hands every TextLink and NavList a renderer for in-app paths
 * (a path starting with "/"); without it, and for anchors ("#id") and absolute URLs, a plain
 * anchor is rendered. The design system never imports the router.
 */
import { createContext, useContext, type ReactNode } from 'react';

/** What a link renderer receives: spread it onto the router's link (map `href` to its prop). */
export interface LinkRenderProps {
  href: string;
  className: string;
  'aria-current': 'page' | undefined;
  'data-active': true | undefined;
  children: ReactNode;
}

export type LinkRenderer = (link: LinkRenderProps) => ReactNode;

const LinkContext = createContext<LinkRenderer | null>(null);

export interface LinkProviderProps {
  /** Renders one in-app link (the router's Link). */
  render: LinkRenderer;
  children: ReactNode;
}

export function LinkProvider({ render, children }: LinkProviderProps) {
  return <LinkContext.Provider value={render}>{children}</LinkContext.Provider>;
}

/** Renders `link` with the app's router link for an in-app path, else as a plain anchor. */
export function useRenderLink(): LinkRenderer {
  const render = useContext(LinkContext);
  return (link) =>
    render && link.href.startsWith('/') ? (
      render(link)
    ) : (
      <a
        href={link.href}
        className={link.className}
        aria-current={link['aria-current']}
        data-active={link['data-active']}
      >
        {link.children}
      </a>
    );
}
