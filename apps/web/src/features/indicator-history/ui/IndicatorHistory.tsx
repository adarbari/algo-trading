/**
 * One indicator's history over the shared window (RG7): its stored value as a line with gaps where
 * nothing is stored, a dashed line where it turns on, a "Signal on" lane from its verdict flag,
 * the market falls and recoveries and the NBER recessions shaded behind it. The window and its
 * control come from the caller (the range is shared by every chart of the page); mounted only
 * when the card is opened, so a closed card reads nothing.
 */
import { Chart, Stack, Text } from '@algotrade/ui';
import type { ReactNode } from 'react';

import {
  indicatorFormat,
  signalLane,
  toHistoryChart,
  useMarketHistory,
  useRegimeEpisodes,
  type HistoryWindow,
  type RegimeIndicator,
} from '@/entities/regime';

/** Points per chart: the server buckets a long window to this many (min and max of each bucket). */
export const HISTORY_POINTS = 600;

export interface IndicatorHistoryProps {
  indicator: RegimeIndicator;
  window: HistoryWindow;
  /** The range control, on the chart's key row. */
  toolbar: ReactNode;
}

export function IndicatorHistory({ indicator, window, toolbar }: IndicatorHistoryProps) {
  const history = useMarketHistory(
    [indicator.feature, indicator.verdictFeature],
    window.start,
    window.end,
    HISTORY_POINTS,
  );
  const episodes = useRegimeEpisodes();
  const line = history.data?.find((h) => h.name === indicator.feature);
  const verdict = history.data?.find((h) => h.name === indicator.verdictFeature);
  const chart = toHistoryChart({
    series: [{ id: indicator.key, label: indicator.plainName, history: line }],
    lanes: [signalLane(verdict)],
    threshold: indicator.threshold === null ? null : { value: indicator.threshold, label: 'on' },
    episodes: episodes.data?.episodes ?? [],
    recessions: episodes.data?.recessions ?? [],
    window,
  });
  return (
    <Stack gap={1}>
      <Chart
        label={`${indicator.plainName}, history`}
        {...chart}
        format={indicatorFormat(indicator)}
        height="sm"
        toolbar={toolbar}
        status={history.isError ? 'error' : history.isPending ? 'loading' : 'ready'}
        errorMessage="The history failed to load."
        onRetry={() => void history.refetch()}
        emptyMessage="Nothing is stored for this indicator in this range."
      />
      <Text size="sm" tone="muted">
        Colors as in the legend above. A gap in the line is a period with no stored value.
      </Text>
    </Stack>
  );
}
