/**
 * The out-of-sample figures of an edge's verdict: win rate, base rate, lift in points and the
 * trades (a `StatStrip`), the same as one `OddsLine`, and the top vs bottom decile with its t.
 * Every number is served (lift in points included); a figure not stored reads as missing.
 */
import { OddsLine, Stack, StatStrip, Text, type StatItem } from '@algotrade/ui';
import type { ReactNode } from 'react';

import type { EdgeVerdict } from '@/entities/edge';
import { GuideHelp } from '@/features/guide-help';

const term = (id: string) => <GuideHelp entry={{ kind: 'term', id }} />;

function Labelled({ text, help }: { text: string; help: string }): ReactNode {
  return (
    <Stack direction="row" gap={1} align="center">
      <Text size="xs" tone="muted">
        {text}
      </Text>
      {term(help)}
    </Stack>
  );
}

export interface EdgeFiguresProps {
  verdict: EdgeVerdict;
}

export function EdgeFigures({ verdict: v }: EdgeFiguresProps) {
  const items: StatItem[] = [
    {
      id: 'win',
      label: <Labelled text="Win rate (OOS)" help="win_rate" />,
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
      format: { kind: 'delta', unit: 'points', digits: 0 },
    },
    {
      id: 'trades',
      label: <Labelled text="Trades (OOS)" help="trades" />,
      value: v.oosTrades,
      format: { kind: 'number' },
    },
    {
      id: 'spread',
      label: <Labelled text="Top vs bottom decile" help="top_vs_bottom_decile" />,
      value: v.decileSpread,
      format: { kind: 'percent', digits: 1 },
      ...(v.decileT == null ? {} : { sub: `t ${v.decileT.toFixed(1)}` }),
    },
  ];
  return (
    <Stack gap={2}>
      <StatStrip label="Out-of-sample result" items={items} />
      {v.winRate != null && v.baseRate != null && v.oosTrades != null && (
        <OddsLine
          hitRate={v.winRate}
          baseRate={v.baseRate}
          sessions={v.oosTrades}
          {...(v.liftPts == null ? {} : { liftPts: v.liftPts })}
          {...(v.basis ? { runLabel: v.basis } : {})}
        />
      )}
    </Stack>
  );
}
