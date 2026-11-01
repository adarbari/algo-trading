/**
 * The footer's risk line: one sentence and the help button of the `risk_statement` Guide term
 * (ADR 0083 decision 4). Its own chunk, so the Guide's help machinery loads after the first paint.
 */
import { Text } from '@algotrade/ui';

import { termHelp } from '@/features/guide-help';

export default function RiskLine() {
  return (
    <>
      <Text size="xs" tone="muted">
        Backtested results are hypothetical. Not investment advice.
      </Text>
      {termHelp('risk_statement')}
    </>
  );
}
