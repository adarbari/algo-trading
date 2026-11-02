/**
 * The rows of an option setup's record (ADR 0088): the cost levels, the stress windows and the
 * years, each a served record worded for a `KeyValue` or `DataTable`. Counts are shown as served
 * ("72 of 100 trades"); no ratio is computed here.
 */
import { formatValue, type KeyValueItem } from '@algotrade/ui';

import type { OptionCostLevel, OptionStress, OptionYear } from '@/entities/edge';
import { termHelp } from '@/features/guide-help';

const pct = (fraction: number, digits = 1): string =>
  formatValue(fraction, { kind: 'percent', digits }).text;
const day = (iso: string): string => formatValue(iso, { kind: 'date', style: 'short' }).text;

const LEVELS = [
  { level: 'mid', label: 'At the middle price', help: 'option_cost_mid' },
  { level: 'effective', label: 'On the worse side', help: 'option_cost_effective' },
  { level: 'full', label: 'At the full spread', help: 'option_cost_full' },
] as const;

/** The cost levels of one period (all, else the first the server sent), in the order mid, effective, full. */
export function costLevels(levels: readonly OptionCostLevel[]): OptionCostLevel[] {
  const period = levels.some((l) => l.period === 'all') ? 'all' : levels[0]?.period;
  return levels.filter((l) => l.period === period);
}

/** A row per stored cost level: the mean return on the cash set aside and the win rate at that level. */
export function costItems(levels: readonly OptionCostLevel[]): KeyValueItem[] {
  const shown = costLevels(levels);
  return LEVELS.flatMap(({ level, label, help: term }) => {
    const row = shown.find((l) => l.level === level);
    if (!row) return [];
    return [
      {
        id: `cost-${level}`,
        label,
        value:
          row.meanRoc == null
            ? 'Not known'
            : `${pct(row.meanRoc)} a trade${row.winRate == null ? '' : `, kept in ${pct(row.winRate, 0)}`}`,
        action: termHelp(term),
      },
    ];
  });
}

/** A row per reference stress window: the worst trade open in it, or that none was. */
export function stressItems(windows: readonly OptionStress[]): KeyValueItem[] {
  return windows.map((w) => ({
    id: `stress-${w.key}`,
    label: `${w.name} (${day(w.start)} to ${day(w.end)})`,
    value:
      w.worst == null ? 'No trade was open' : `${pct(w.worst)} worst, of ${String(w.trades)} open`,
    action: termHelp('option_stress'),
  }));
}

/** A row per year of the setup's history: its trades, the typical one and how many kept the premium. */
export function yearItems(years: readonly OptionYear[]): KeyValueItem[] {
  return years.map((y) => ({
    id: `year-${String(y.year)}`,
    label: String(y.year),
    value: [
      `${String(y.trades)} trades`,
      y.typical == null ? null : `typical ${pct(y.typical)}`,
      `${String(y.kept)} kept the premium`,
    ]
      .filter((part) => part != null)
      .join(', '),
  }));
}
