/**
 * The live preview of a draft (POST /screeners/preview): the run summary, decision counts,
 * funnel per gating rule and top rows, shaped for the Builder's panels. Pure.
 */
import type { components } from '@/shared/api';

export type ScreenPreview = components['schemas']['ScreenPreview'];
export type PreviewRow = components['schemas']['PreviewRow'];
export type PreviewSummary = components['schemas']['PreviewSummary'];
export type NarrowMiss = components['schemas']['NarrowMiss'];
export type FunnelStep = components['schemas']['FunnelStep'];

/** Decisions in the order the preview lists them. */
const DECISION_ORDER = ['QUALIFIED', 'WATCH', 'LIQUIDITY_RISK', 'EVENT_RISK', 'REJECT', 'SKIPPED'];

/** The decision counts, in display order, omitting decisions nobody got. */
export function decisionCounts(preview: ScreenPreview): { decision: string; count: number }[] {
  const known = DECISION_ORDER.flatMap((decision) => {
    const count = preview.decisions[decision];
    return count ? [{ decision, count }] : [];
  });
  const other = Object.entries(preview.decisions)
    .filter(([decision, count]) => count > 0 && !DECISION_ORDER.includes(decision))
    .map(([decision, count]) => ({ decision, count }));
  return [...known, ...other];
}

/** The rows' extra column names (`[columns]` of the screen), in first-seen order. */
export function extraColumns(rows: readonly PreviewRow[]): string[] {
  return [...new Set(rows.flatMap((row) => Object.keys(row.columns)))];
}

/** The narrow misses grouped by criterion, biggest group first. */
export function narrowMissGroups(
  misses: readonly NarrowMiss[],
): { criterionId: string; field: string; misses: NarrowMiss[] }[] {
  const groups = new Map<string, { criterionId: string; field: string; misses: NarrowMiss[] }>();
  for (const miss of misses) {
    const group = groups.get(miss.criterion_id) ?? {
      criterionId: miss.criterion_id,
      field: miss.field,
      misses: [],
    };
    group.misses.push(miss);
    groups.set(miss.criterion_id, group);
  }
  return [...groups.values()].sort((a, b) => b.misses.length - a.misses.length);
}
