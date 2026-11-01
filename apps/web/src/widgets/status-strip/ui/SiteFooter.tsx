/**
 * The footer of every page: the data-status pill (which session's data the pages show and
 * whether it is complete) and the one-line risk statement with its help button. The statement's words are the Guide's (term `risk_statement`; ADR 0051).
 */
import { Stack } from '@algotrade/ui';

import { DataStatusPill } from './DataStatusPill';
import RiskLine from './RiskLine';

export interface SiteFooterProps {
  /** The viewer is an admin: the pill's detail also shows the causes the server sent. */
  admin: boolean;
}

export default function SiteFooter({ admin }: SiteFooterProps) {
  return (
    <Stack direction="row" gap={4} align="center" wrap>
      <DataStatusPill admin={admin} />
      <RiskLine />
    </Stack>
  );
}
