/**
 * What a Screeners row shows of a run, chosen from the served values: the new / dropped counts
 * since the previous run and the decision segments of the bar. Pure; nothing is recounted.
 */
import type { StackedBarSegment } from '@algotrade/ui';

import {
  decisionLabel,
  decisionTone,
  DEFAULT_DECISIONS,
  orderedDecisions,
} from '@/entities/screen';

export interface Changes {
  added: number;
  dropped: number;
}

/** The served `new` / `dropped` counts; null when the run has no previous run to compare with. */
export function changesOf(changes: readonly { change: string; count: number }[]): Changes | null {
  if (changes.length === 0) return null;
  const count = (name: string) => changes.find((c) => c.change === name)?.count ?? 0;
  return { added: count('new'), dropped: count('dropped') };
}

/**
 * The bar's segments: the picks' decisions (qualified, watch, event risk, paused ...) in display
 * order. The rejects stay out: thousands of them would shrink every pick to a sliver.
 */
export function decisionSegments(
  decisions: readonly { decision: string; count: number }[],
): StackedBarSegment[] {
  return orderedDecisions(decisions)
    .filter((d) => DEFAULT_DECISIONS.includes(d.decision))
    .map((d) => ({
      id: d.decision,
      label: decisionLabel(d.decision),
      value: d.count,
      tone: decisionTone(d.decision),
    }));
}
