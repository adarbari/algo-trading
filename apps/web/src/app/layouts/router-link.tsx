/**
 * The router's link for the design system's links (`LinkProvider`): an in-app path, with an
 * optional query string ("/explore?tab=features") and anchor ("/guide/edges#set-aside"), becomes a router Link with its search params,
 * so a click navigates without a page load and the link stays a real anchor.
 */
import type { LinkRenderProps } from '@algotrade/ui';
import { Link } from '@tanstack/react-router';

export function renderRouterLink({ href, children, ...props }: LinkRenderProps) {
  // "/guide/edges#set-aside": the path, then the anchor; a bare "#anchor" stays the path itself.
  const hashAt = href.indexOf('#');
  const base = hashAt > 0 ? href.slice(0, hashAt) : href;
  const [to = '/', query] = base.split('?');
  const search = query ? Object.fromEntries(new URLSearchParams(query)) : undefined;
  return (
    <Link
      to={to}
      {...(search ? { search } : {})}
      {...(hashAt > 0 ? { hash: href.slice(hashAt + 1) } : {})}
      {...props}
    >
      {children}
    </Link>
  );
}
