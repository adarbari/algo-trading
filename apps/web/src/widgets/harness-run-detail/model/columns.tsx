/**
 * The columns of one run's stored rows: a variant at a horizon over one slice, with its measures
 * as the run left them (empty: not stored). Rows of an exploratory run say so.
 */
import { Mono, StatusBadge, type DataTableColumn } from '@algotrade/ui';

import { rowLabel, type HarnessLostInput, type HarnessRow } from '@/entities/harness-run';
import { GuideHelp } from '@/features/guide-help';

const term = (id: string) => <GuideHelp entry={{ kind: 'term', id }} />;
const COUNT = { kind: 'number' } as const;
const RATE = { kind: 'percent', digits: 1 } as const;
const FIGURE = { kind: 'number', digits: 2 } as const;

export function rowColumns(): DataTableColumn<HarnessRow>[] {
  return [
    {
      id: 'variant',
      header: 'Variant',
      value: (r) => rowLabel(r),
      hideable: false,
      grow: true,
      essential: true,
    },
    {
      id: 'horizon',
      header: 'Horizon',
      value: (r) => r.horizonSessions,
      format: COUNT,
      align: 'end',
      essential: true,
    },
    {
      id: 'slice',
      header: 'Slice',
      value: (r) => `${r.sliceKind} ${r.sliceValue}`,
      cell: ({ row }) => (
        <>
          <Mono size="sm">{`${row.sliceKind} ${row.sliceValue}`}</Mono>
          {row.exploratory && <StatusBadge tone="warning">EXPLORATORY</StatusBadge>}
        </>
      ),
      essential: true,
    },
    {
      id: 'sessions',
      header: 'Sessions',
      value: (r) => r.sessions ?? null,
      format: COUNT,
      align: 'end',
    },
    { id: 'picks', header: 'Picks', value: (r) => r.picks ?? null, format: COUNT, align: 'end' },
    { id: 'hits', header: 'Hits', value: (r) => r.hits ?? null, format: COUNT, align: 'end' },
    {
      id: 'trials',
      header: 'Trials',
      headerAction: term('trial_log'),
      value: (r) => r.trials ?? null,
      format: COUNT,
      align: 'end',
    },
    {
      id: 'hitRate',
      header: 'Hit rate',
      headerAction: term('hit_rate'),
      value: (r) => r.hitRate ?? null,
      format: RATE,
      align: 'end',
    },
    {
      id: 'baseRate',
      header: 'Base rate',
      headerAction: term('base_rate'),
      value: (r) => r.baseRate ?? null,
      format: RATE,
      align: 'end',
    },
    {
      id: 'lift',
      header: 'Lift',
      headerAction: term('lift'),
      value: (r) => r.lift ?? null,
      format: FIGURE,
      align: 'end',
    },
    {
      id: 'decile',
      header: 'Decile spread',
      headerAction: term('decile_spread'),
      value: (r) => r.decileSpread ?? null,
      format: { kind: 'percent', digits: 2 },
      align: 'end',
    },
  ];
}

/** The input tables a variant had no data in: the sessions lost to each (unmeasured, not a miss). */
export function lostColumns(): DataTableColumn<HarnessLostInput>[] {
  return [
    { id: 'variant', header: 'Variant', value: (l) => l.variant, hideable: false, grow: true },
    {
      id: 'horizon',
      header: 'Horizon',
      value: (l) => l.horizon,
      format: COUNT,
      align: 'end',
    },
    { id: 'table', header: 'Missing table', value: (l) => l.table, essential: true },
    {
      id: 'sessions',
      header: 'Sessions lost',
      value: (l) => l.sessions,
      format: COUNT,
      align: 'end',
      essential: true,
    },
  ];
}
