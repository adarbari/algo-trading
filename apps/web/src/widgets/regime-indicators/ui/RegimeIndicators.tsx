/**
 * The regime's indicator cards in two lists, slow (macro, weekly) and fast (market, daily):
 * each an `IndicatorRow` with the plain name, what it measures, its current value (or why it is
 * unknown) and its verdict; expanded, why it matters, what "on" means, what it did before past
 * falls, its lead time, its false alarms and its links. Data, empty and error states.
 */
import { IndicatorRow, Panel, Skeleton, Stack } from '@algotrade/ui';

import { shownValue, valueFormat } from '@/entities/feature';
import {
  indicatorChange,
  indicatorsOfPace,
  indicatorStatus,
  useRegime,
  type Regime,
  type RegimeIndicator,
} from '@/entities/regime';

import { IndicatorDetail } from './IndicatorDetail';

const isScalar = (value: unknown): value is string | number | boolean =>
  typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean';

function Row({ indicator }: { indicator: RegimeIndicator }) {
  const known = indicator.unknown === null && isScalar(indicator.value);
  const shown = known ? shownValue(indicator.value) : null;
  const change = indicatorChange(indicator);
  const reason = indicator.unknown?.detail;
  return (
    <IndicatorRow
      status={indicatorStatus(indicator.status)}
      name={indicator.plainName}
      technicalName={indicator.technicalName}
      description={reason ? `${indicator.oneLiner} Unknown: ${reason}` : indicator.oneLiner}
      value={typeof shown === 'string' || typeof shown === 'number' ? shown : null}
      format={valueFormat({ format: indicator.format ?? 'TEXT' })}
      {...(change ? { changed: change.change, changedLabel: change.label } : {})}
    >
      <IndicatorDetail indicator={indicator} />
    </IndicatorRow>
  );
}

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
            <Row indicator={indicator} />
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
