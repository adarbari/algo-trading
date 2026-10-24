/**
 * The ledger's older period vocabulary read off the filters in force: the CSV file is still the
 * period's trades (its route takes a period, not filters), and the read keeps `ALL` (the
 * backtest's trades) as its default so a viewer's own `record` filter wins over it (ADR 0082).
 */
import type { AppliedFilter } from '@/entities/filter';
import type { TradePeriod } from '@/entities/edge';

const valuesOf = (filters: readonly AppliedFilter[], id: string): readonly string[] =>
  filters.find((f) => f.id === id && f.active)?.values ?? [];

/** The period the filters in force stand for: live only, a side of the backtest, else all. */
export function periodOf(filters: readonly AppliedFilter[]): TradePeriod {
  const record = valuesOf(filters, 'record');
  if (record.length === 1 && record[0] === 'live') return 'LIVE';
  const sample = valuesOf(filters, 'in_sample');
  if (sample.length === 1 && !record.includes('live')) {
    if (sample[0] === 'yes') return 'IN_SAMPLE';
    if (sample[0] === 'no') return 'OUT_OF_SAMPLE';
  }
  return 'ALL';
}
