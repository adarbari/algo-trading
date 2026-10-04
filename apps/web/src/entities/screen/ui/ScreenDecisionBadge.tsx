/** A rule-screen decision as a badge; SKIPPED (data missing) and REJECT read as neutral. */
import { DecisionBadge } from '@/entities/idea';

export function ScreenDecisionBadge({ decision }: { decision: string }) {
  return <DecisionBadge decision={decision} />;
}
