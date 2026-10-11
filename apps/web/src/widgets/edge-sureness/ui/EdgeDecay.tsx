/**
 * Decay: the edge's number at each stage, the paper's published figure, in-sample, out-of-sample
 * and the live record (its own read, `edgeResult.decay`), as signed bars of one statistic. A
 * stage with no value says its state in words instead of a bar of zero (not given, not stored,
 * not comparable, hidden, not measured live); the number of trades behind a measured bar is
 * written beside it. Every value, count and state is the server's.
 */
import { BarList, ExternalLink, Panel, Stack, Text, type BarListItem } from '@algotrade/ui';

import {
  barStateLabel,
  measureLabel,
  periodLabel,
  useEdgeDecay,
  type DecayBar,
  type EdgeResultDecay,
} from '@/entities/edge';
import { termHelp } from '@/features/guide-help';

const item = (bar: DecayBar): BarListItem => {
  const label =
    bar.n == null ? periodLabel(bar.period) : `${periodLabel(bar.period)} · n=${String(bar.n)}`;
  return bar.state === 'measured' && bar.value != null
    ? { id: bar.period, label, value: bar.value }
    : { id: bar.period, label, value: 0, display: barStateLabel(bar.state) };
};

const formatOf = (decay: EdgeResultDecay) =>
  decay.unit === 'points'
    ? ({ kind: 'delta', unit: 'points', digits: 1 } as const)
    : ({ kind: 'delta', unit: 'percent', digits: 1 } as const);

export interface EdgeDecayProps {
  edgeId: string;
}

export function EdgeDecay({ edgeId }: EdgeDecayProps) {
  const query = useEdgeDecay(edgeId);
  const decay = query.data;
  if (query.isPending) {
    return (
      <Panel
        title="Decay"
        headingLevel={3}
        actions={termHelp('decay')}
        state="loading"
        loadingLabel="Loading the decay…"
      />
    );
  }
  if (query.isError) {
    return (
      <Panel
        title="Decay"
        headingLevel={3}
        actions={termHelp('decay')}
        state="error"
        errorMessage="The decay failed to load."
        onRetry={() => void query.refetch()}
      />
    );
  }
  return (
    <Panel
      title="Decay"
      headingLevel={3}
      actions={termHelp('decay')}
      state={decay ? 'ready' : 'empty'}
      emptyMessage="No decay: the verdict has no basis yet."
    >
      {decay && (
        <Stack gap={2}>
          <Text size="xs" tone="muted">
            {measureLabel(decay.measure)}
          </Text>
          <BarList
            label="Decay by stage"
            items={decay.bars.map(item)}
            diverging
            format={formatOf(decay)}
          />
          {decay.published && (
            <Text size="xs" tone="muted">
              <ExternalLink href={decay.published.source.url} size="inherit">
                {decay.published.source.title}
              </ExternalLink>
            </Text>
          )}
        </Stack>
      )}
    </Panel>
  );
}
