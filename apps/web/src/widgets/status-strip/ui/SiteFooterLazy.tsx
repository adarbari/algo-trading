/**
 * The footer of every page: the one-line risk statement with its Guide pages (the risk statement
 * and the methodology and conflicts page; ADR 0083 decision 4) at once, then, from the first
 * interaction (pointer, key, touch or scroll), the data-status pill (`SiteFooter`). The late part
 * keeps the pill's code out of every page's first load.
 */
import { Stack, Text, TextLink } from '@algotrade/ui';
import { lazy, Suspense, useEffect, useState } from 'react';

import { startPath, termPath } from '@/entities/guide';

import type { SiteFooterProps } from './SiteFooter';

const Late = lazy(() => import('./SiteFooter'));

const EVENTS = ['pointerdown', 'pointermove', 'keydown', 'scroll', 'touchstart'] as const;

export type { SiteFooterProps };

export function SiteFooter(props: SiteFooterProps) {
  const [engaged, setEngaged] = useState(false);
  useEffect(() => {
    if (engaged) return undefined;
    const engage = () => {
      setEngaged(true);
    };
    for (const name of EVENTS) window.addEventListener(name, engage, { passive: true, once: true });
    return () => {
      for (const name of EVENTS) window.removeEventListener(name, engage);
    };
  }, [engaged]);
  return (
    <Stack direction="row" gap={4} align="center" wrap>
      {engaged && (
        <Suspense fallback={null}>
          <Late {...props} />
        </Suspense>
      )}
      <Text size="xs" tone="muted">
        Backtested results are hypothetical. Not investment advice.
      </Text>
      <TextLink href={termPath('risk_statement')} size="sm">
        Risk statement
      </TextLink>
      <TextLink href={startPath('methodology_and_conflicts')} size="sm">
        Methodology and conflicts
      </TextLink>
    </Stack>
  );
}
