/**
 * A decision (QUALIFIED, WATCH, EVENT_RISK, ...) as a toned badge; SKIPPED (data missing) and
 * REJECT read as neutral.
 */
import { StatusBadge } from '@algotrade/ui';

import { decisionLabel, decisionTone } from '../model/decisions';

export function DecisionBadge({ decision }: { decision: string }) {
  return <StatusBadge tone={decisionTone(decision)}>{decisionLabel(decision)}</StatusBadge>;
}
