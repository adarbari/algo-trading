/** The first day of a chart window (3M, 1Y, 2Y, All), counted back from today. */
import type { ChartRange } from '@algotrade/ui';

import { addMonths, todayIso } from '@/shared/lib';

/** Earlier than any stored history: "All" asks for everything. */
export const ALL_HISTORY = '1990-01-01';

const MONTHS: Readonly<Record<ChartRange, number | null>> = {
  '3M': 3,
  '1Y': 12,
  '2Y': 24,
  All: null,
};

export function rangeFrom(range: ChartRange, today: string = todayIso()): string {
  const months = MONTHS[range];
  return months === null ? ALL_HISTORY : addMonths(today, -months);
}
