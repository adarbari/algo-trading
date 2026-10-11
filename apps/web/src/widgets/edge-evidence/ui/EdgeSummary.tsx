/**
 * The out-of-sample result of an edge's verdict at a glance: win rate, base rate, lift, trades
 * with what the verdict needs, and the share of random-pick backtests beaten (a `StatStrip`), and
 * the same as one `OddsLine`. Every number is served (lift in points included); a figure not
 * stored reads as missing, and without a win rate, base rate and trades the line is left out.
 */
import { OddsLine, Stack, StatStrip, type StatItem } from '@algotrade/ui';

import type { EdgeVerdict } from '@/entities/edge';
import { Labelled, termHelp } from '@/features/guide-help';

export interface EdgeSummaryProps {
  verdict: EdgeVerdict;
}

export function EdgeSummary({ verdict: v }: EdgeSummaryProps) {
  const needed = v.evidence?.needed;
  const items: StatItem[] = [
    {
      id: 'win',
      label: <Labelled text="Win rate · OOS" help="win_rate" />,
      value: v.winRate,
      format: { kind: 'percent', digits: 0 },
    },
    {
      id: 'base',
      label: <Labelled text="Base rate" help="base_rate" />,
      value: v.baseRate,
      format: { kind: 'percent', digits: 0 },
    },
    {
      id: 'lift',
      label: <Labelled text="Lift" help="lift" />,
      value: v.liftPts,
      format: { kind: 'delta', unit: 'points', digits: 1 },
    },
    {
      id: 'trades',
      label: <Labelled text="Trades · OOS" help="trades" />,
      value: v.oosTrades,
      format: { kind: 'number' },
      ...(needed == null ? {} : { sub: `${String(needed)} needed` }),
    },
    {
      id: 'beats',
      label: <Labelled text="Beats random" help="robustness" />,
      value: v.robustness?.beats ?? null,
      format: { kind: 'percent', digits: 0 },
    },
  ];
  const run = [v.basis, v.trials == null ? null : `${String(v.trials)} variants tried`]
    .filter((part) => part != null)
    .join(' · ');
  return (
    <Stack gap={2}>
      <StatStrip label="Out-of-sample result" items={items} />
      {v.winRate != null && v.baseRate != null && v.oosTrades != null && (
        <OddsLine
          hitRate={v.winRate}
          baseRate={v.baseRate}
          sessions={v.oosTrades}
          info={termHelp('base_rate')}
          {...(v.liftPts == null ? {} : { liftPts: v.liftPts })}
          {...(run ? { runLabel: run } : {})}
        />
      )}
    </Stack>
  );
}
