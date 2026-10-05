/**
 * What the drill-down shows for one cell: the run behind it (the latest run of the dataset's
 * job that recorded items), its items by status as bar segments (else present vs missing
 * rows), the fetch-priority tiers the chains run recorded, and up to ten example items per
 * issue group.
 */
import { formatValue, type BarListItem, type StackedBarSegment } from '@algotrade/ui';

import type { CellDetail } from '@/entities/ingestion';
import { segmentTone, toRunDetail, type RunDetail } from '@/entities/run';

/** The run whose items explain the cell. */
export function primaryRun(detail: CellDetail): RunDetail | undefined {
  const own = detail.runs.filter((r) => r.job === detail.job);
  const run = own.filter((r) => r.itemsTotal > 0).at(-1) ?? own.at(-1) ?? detail.runs.at(-1);
  return run ? toRunDetail(run) : undefined;
}

const label = (code: string) =>
  code
    .replace(/_/g, ' ')
    .toLowerCase()
    .replace(/^\w/, (c) => c.toUpperCase());

export function statusSegments(
  detail: CellDetail,
  run: RunDetail | undefined,
): StackedBarSegment[] {
  if (run && run.itemsTotal > 0) {
    return Object.entries(run.itemsByStatus).map(([code, n]) => ({
      id: code,
      label: label(code),
      value: n,
      tone: segmentTone(code),
    }));
  }
  const { present, expected } = detail.cell;
  return [
    { id: 'present', label: 'Present', value: present, tone: 'positive' },
    ...(expected !== null && expected > present
      ? [{ id: 'missing', label: 'Missing', value: expected - present, tone: 'negative' as const }]
      : []),
  ];
}

const TIER_LABELS: Record<string, string> = {
  priority: 'Priority (S&P 500 + pinned)',
  liquidity: 'Liquid names',
  rest: 'Rest',
};

/** Underlyings per fetch-priority tier (``stats.order_tiers`` of a chains run), in fetch order. */
export function fetchTiers(run: RunDetail | undefined): BarListItem[] {
  const tiers = run?.stats['order_tiers'];
  if (!tiers || typeof tiers !== 'object') return [];
  return Object.entries(tiers as Record<string, unknown>)
    .filter((entry): entry is [string, number] => typeof entry[1] === 'number')
    .map(([tier, n]) => ({ id: tier, label: TIER_LABELS[tier] ?? tier, value: n }));
}

/** `ACIU · ALLT · AOSL · … 512 more`. */
export function examplesText(examples: readonly string[], count: number): string {
  const more = count - examples.length;
  const extra = more > 0 ? ` · … ${formatValue(more, { kind: 'number' }).text} more` : '';
  return `${examples.join(' · ')}${extra}`;
}
