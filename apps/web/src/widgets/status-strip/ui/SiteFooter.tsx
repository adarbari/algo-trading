/**
 * The footer of every page: the data-status pill (which session's data the pages show and
 * whether it is complete) and the one-line risk statement with its help button (`RiskLine`, loaded after
 * the first paint). The statement's words are the Guide's (term `risk_statement`; ADR 0051).
 */
import { Stack } from '@algotrade/ui';
import { lazy, Suspense } from 'react';

import { DataStatusPill } from './DataStatusPill';

const RiskLine = lazy(() => import('./RiskLine'));

export interface SiteFooterProps {
  /** The viewer is an admin: the pill's detail also shows the causes the server sent. */
  admin: boolean;
}

export function SiteFooter({ admin }: SiteFooterProps) {
  return (
    <Stack direction="row" gap={4} align="center" wrap>
      <DataStatusPill admin={admin} />
      <Suspense fallback={null}>
        <RiskLine />
      </Suspense>
    </Stack>
  );
}
