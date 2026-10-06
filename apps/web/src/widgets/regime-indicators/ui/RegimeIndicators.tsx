/**
 * The regime's indicator cards in two lists, slow (macro, weekly) and fast (market, daily):
 * each an `IndicatorCard` (name and verdict, range meter, linked how-line, sources with their
 * provenance, history chart, and the detail of why it matters). Data, empty and error states.
 */
import { Panel, Skeleton, Stack } from '@algotrade/ui';

import { indicatorsOfPace, useRegime, type Regime } from '@/entities/regime';

import { IndicatorCard } from './IndicatorCard';

function PaceList({
  regime,
  pace,
  title,
  description,
}: {
  regime: Regime;
  pace: 'slow' | 'fast';
  title: string;
  description: string;
}) {
  const indicators = indicatorsOfPace(regime, pace);
  return (
    <Panel
      title={title}
      description={description}
      flush
      state={indicators.length === 0 ? 'empty' : 'ready'}
      emptyMessage="No indicator cards in this list."
    >
      <Stack as="ul" gap={0}>
        {indicators.map((indicator) => (
          <Stack as="li" key={indicator.key}>
            <IndicatorCard
              indicator={indicator}
              session={regime.session}
              explainable={regime.label !== 'UNKNOWN'}
            />
          </Stack>
        ))}
      </Stack>
    </Panel>
  );
}

export function RegimeIndicators() {
  const regime = useRegime();
  if (regime.isPending || regime.isError || regime.data === null) {
    const state = regime.isError ? 'error' : regime.isPending ? 'ready' : 'empty';
    return (
      <Panel
        title="Warning signs"
        state={state}
        emptyMessage="No regime is stored yet, so there are no warning signs to show."
        errorMessage="The warning signs failed to load."
        onRetry={() => void regime.refetch()}
      >
        <Skeleton variant="table" rows={4} columns={2} label="Loading the warning signs" />
      </Panel>
    );
  }
  return (
    <Stack gap={3}>
      <PaceList
        regime={regime.data}
        pace="slow"
        title="Slow-moving warning signs"
        description="Credit, jobs and the yield curve: they change over weeks"
      />
      <PaceList
        regime={regime.data}
        pace="fast"
        title="Fast-moving market signs"
        description="Trend, volatility and breadth: they change daily"
      />
    </Stack>
  );
}
