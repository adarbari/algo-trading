/**
 * The footer of every page, loaded after the first paint: it sits below the content, so its data-status
 * pill and risk line (`SiteFooter`) stay out of the entry chunk.
 */
import { lazy, Suspense } from 'react';

import type { SiteFooterProps } from './SiteFooter';

const Footer = lazy(() => import('./SiteFooter'));

export type { SiteFooterProps };

export function SiteFooter(props: SiteFooterProps) {
  return (
    <Suspense fallback={null}>
      <Footer {...props} />
    </Suspense>
  );
}
