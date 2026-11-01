/**
 * The footer of every page: the data-status pill (which session's data the pages show and
 * whether it is complete) and the one-line risk statement with its help button. The statement's
 * words are the Guide's (term `risk_statement`); this file only places them (ADR 0051).
 */
import { Text } from '@algotrade/ui';

import { termHelp } from '@/features/guide-help';

import { DataStatusPill } from './DataStatusPill';

export interface SiteFooterProps {
  /** The viewer is an admin: the pill's detail also shows the causes the server sent. */
  admin: boolean;
}

export function SiteFooter({ admin }: SiteFooterProps) {
  return (
    <>
      <DataStatusPill admin={admin} />
      <Text size="xs" tone="muted">
        Backtested results are hypothetical. Not investment advice.
      </Text>
      {termHelp('risk_statement')}
    </>
  );
}
