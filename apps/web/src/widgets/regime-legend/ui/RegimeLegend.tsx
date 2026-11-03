/**
 * The key to every regime chart, written once (RG7): what the lines are, what each lane under a
 * chart says (regime, signal, evidence) and what is shaded behind the lines (the market's falls
 * and recoveries, the NBER recessions, hatched so overlapping spans stay readable). The charts
 * keep their own keys; this explains the colors in words, and the indicator charts point here.
 */
import { Heading, Legend, Panel, Stack } from '@algotrade/ui';
import type { ReactNode } from 'react';

import { BAND_LABELS, LANE_LABELS, plainLabel, regimeTone } from '@/entities/regime';
import { termHelp } from '@/features/guide-help';

const REGIME_LABELS = ['CALM', 'CAUTION', 'STRESS', 'CRISIS', 'UNKNOWN'] as const;

function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Stack gap={1}>
      <Heading level={3} size="sm" tone="muted">
        {title}
      </Heading>
      {children}
    </Stack>
  );
}

export function RegimeLegend() {
  return (
    <Panel
      title="How to read the charts"
      description="The same colors on every chart of this page"
      actions={termHelp('regime_chart_key')}
    >
      <Stack gap={3}>
        <Stack direction="row" gap={4} wrap>
          <Group title="Shaded behind the lines">
            <Stack gap={1}>
              <Legend
                swatch="cell"
                size="xs"
                label="Falls and recoveries"
                items={[
                  { label: BAND_LABELS.fall, tone: 'negative' },
                  { label: BAND_LABELS.recovery, tone: 'positive' },
                ]}
              />
              <Legend
                swatch="hatch"
                size="xs"
                label="Recessions"
                items={[{ label: BAND_LABELS.recession, tone: 'neutral' }]}
              />
            </Stack>
          </Group>
          <Group title="Regime strip (the scores chart)">
            <Legend
              swatch="cell"
              size="xs"
              label="Regime"
              items={REGIME_LABELS.map((label) => ({
                label: plainLabel(label),
                tone: regimeTone(label),
              }))}
            />
          </Group>
          <Group title="Signal strip (each indicator chart)">
            <Legend
              swatch="cell"
              size="xs"
              label="Signal"
              items={[
                { label: LANE_LABELS.signalOn, tone: 'warning' },
                { label: LANE_LABELS.noData, tone: 'neutral' },
              ]}
            />
          </Group>
          <Group title="Evidence strip (the scores chart)">
            <Legend
              swatch="cell"
              size="xs"
              label="Evidence"
              items={[
                { label: LANE_LABELS.fullEvidence, tone: 'info' },
                { label: LANE_LABELS.partialEvidence, tone: 'warning' },
                { label: LANE_LABELS.noEvidence, tone: 'neutral' },
              ]}
            />
          </Group>
        </Stack>
              </Stack>
    </Panel>
  );
}
