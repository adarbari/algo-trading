/** A decision (QUALIFIED, WATCH, EVENT_RISK, ...) as a toned badge. */
import { StatusBadge } from '@algotrade/ui';

import { decisionLabel, decisionTone } from '../model/idea';

export function DecisionBadge({ decision }: { decision: string }) {
  return <StatusBadge tone={decisionTone(decision)}>{decisionLabel(decision)}</StatusBadge>;
}
