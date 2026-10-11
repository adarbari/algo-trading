/**
 * Robustness: the edge's out-of-sample lift (a marker) among the lifts of the random-pick
 * backtests (a `Distribution`), with the server's sentence under it, then the multiple-testing
 * line: the variants tried, the deflated Sharpe, the Sharpe after the haircut and the chance of
 * overfitting. Every figure, bin and sentence is served; a figure the run did not store reads
 * as missing, and a run that drew no random picks shows an empty panel.
 */
import { Distribution, KeyValue, Panel, Stack, Text, type KeyValueItem } from '@algotrade/ui';

import type { EdgeVerdict } from '@/entities/edge';
import { Labelled, termHelp } from '@/features/guide-help';

const NUMBER = { kind: 'number', digits: 2 } as const;

function lines(v: EdgeVerdict): KeyValueItem[] {
  return [
    {
      id: 'variants',
      label: <Labelled text="Variants tried" help="variants_tried" />,
      value: v.trials,
      format: { kind: 'number' },
    },
    {
      id: 'dsr',
      label: <Labelled text="Deflated Sharpe" help="deflated_sharpe" />,
      value: v.deflatedSharpe,
      format: NUMBER,
    },
    {
      id: 'haircut',
      label: <Labelled text="Haircut Sharpe" help="haircut_sharpe" />,
      value: v.haircut?.haircutSharpe ?? null,
      format: NUMBER,
    },
    {
      id: 'pbo',
      label: <Labelled text="Chance of overfitting" help="overfitting_probability" />,
      value: v.pbo,
      format: NUMBER,
    },
  ];
}

export interface EdgeRobustnessProps {
  verdict: EdgeVerdict;
}

export function EdgeRobustness({ verdict }: EdgeRobustnessProps) {
  const robustness = verdict.robustness;
  return (
    <Panel
      title="Robustness"
      headingLevel={3}
      state={robustness ? 'ready' : 'empty'}
      emptyMessage="No random-pick backtests for this result."
      actions={termHelp('robustness')}
    >
      {robustness && (
        <Stack gap={3}>
          <Stack gap={2}>
            <Distribution
              label="Lift of random-pick backtests"
              bins={robustness.bins}
              format={{ kind: 'number', digits: 2 }}
              markers={[{ value: robustness.lift, label: 'This edge', tone: 'accent' }]}
            />
            <Text size="sm">{robustness.summary}</Text>
          </Stack>
          <KeyValue label="Multiple testing" items={lines(verdict)} alignValues="end" />
          {verdict.haircut && (
            <Text size="xs" tone="muted">
              {verdict.haircut.summary}
            </Text>
          )}
        </Stack>
      )}
    </Panel>
  );
}
