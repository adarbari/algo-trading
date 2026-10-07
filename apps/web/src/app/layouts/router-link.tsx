/**
 * The router's link for the design system's links (`LinkProvider`): an in-app path, with an
 * optional query string ("/explore?tab=features"), becomes a router Link with its search params,
 * so a click navigates without a page load and the link stays a real anchor.
 */
import type { LinkRenderProps } from '@algotrade/ui';
import { Link } from '@tanstack/react-router';

export function renderRouterLink({ href, children, ...props }: LinkRenderProps) {
  const [to = '/', query] = href.split('?');
  const search = query ? Object.fromEntries(new URLSearchParams(query)) : undefined;
  return (
    <Link to={to} {...(search ? { search } : {})} {...props}>
      {children}
    </Link>
  );
}
