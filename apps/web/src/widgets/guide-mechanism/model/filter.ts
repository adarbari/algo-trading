/**
 * Narrowing the edges of one mechanism page by asset, side, holding band and status: which edges
 * pass, and the options each filter offers (the values its own edges carry, with the server's
 * words for them). It only selects rows the server sent.
 */
import { edgeSideText, edgeStatusText, type EdgeRowValue } from '@/entities/guide';

export interface EdgeFacts extends EdgeRowValue {
  asset: string;
  holdingBand: string;
}

export type EdgeFilters = {
  asset?: string | undefined;
  side?: string | undefined;
  holding?: string | undefined;
  status?: string | undefined;
};

export const FILTER_LABELS = {
  status: 'Status',
  asset: 'Asset',
  side: 'Side',
  holding: 'Holding',
} as const;

/** An edge passes when it matches every filter in force. */
export function edgeMatches(edge: EdgeFacts, filters: EdgeFilters): boolean {
  return (
    (!filters.asset || edge.asset === filters.asset) &&
    (!filters.side || edge.side === filters.side) &&
    (!filters.holding || edge.holdingBand === filters.holding) &&
    (!filters.status || edge.status === filters.status)
  );
}

export interface FilterOption {
  value: string;
  label: string;
}

const capitalised = (text: string): string => text.charAt(0).toUpperCase() + text.slice(1);

/** The options of each filter: the distinct values among the edges, with how many carry each. */
export function filterOptions(
  edges: readonly EdgeFacts[],
): Record<keyof EdgeFilters, FilterOption[]> {
  const options = (
    value: (e: EdgeFacts) => string,
    label: (e: EdgeFacts) => string,
  ): FilterOption[] => {
    const seen = new Map<string, { label: string; count: number }>();
    for (const edge of edges) {
      const entry = seen.get(value(edge));
      if (entry) entry.count += 1;
      else seen.set(value(edge), { label: label(edge), count: 1 });
    }
    return [...seen].map(([v, e]) => ({ value: v, label: `${e.label} · ${String(e.count)}` }));
  };
  return {
    status: options(
      (e) => e.status,
      (e) => edgeStatusText(e.status),
    ),
    asset: options(
      (e) => e.asset,
      (e) => e.assetText,
    ),
    side: options(
      (e) => e.side,
      (e) => edgeSideText(e.side),
    ),
    holding: options(
      (e) => e.holdingBand,
      (e) => capitalised(e.holdingBand),
    ),
  };
}
