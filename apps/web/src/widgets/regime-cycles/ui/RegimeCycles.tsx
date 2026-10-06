/**
 * "Scores through the cycles" (RG7): the macro risk and market stress scores over the stored
 * history as two lines with a dashed line where a score counts as high, a strip of the regime
 * label under them and a strip of how much of the evidence was known, with the market's falls,
 * recoveries and the NBER recessions shaded behind. The window is shared with every history chart
 * of the page (the range control here and on each card). It is mounted with the page (no
 * scroll-into-view hook exists yet), so it reads its history once. Data, empty and error states.
 */
import { Chart, Panel, Skeleton } from '@algotrade/ui';

import {
  evidenceLane,
  regimeLabelFeature,
  regimeLane,
  toHistoryChart,
  useMarketHistory,
  useRegime,
  useRegimeEpisodes,
  type Regime,
} from '@/entities/regime';
import { RegimeRangeControl, useRegimeRange } from '@/features/regime-range';

/** Points per chart: the server buckets a long window to this many (min and max of each bucket). */
const POINTS = 600;

function CyclesPanel({ regime }: { regime: Regime }) {
  const range = useRegimeRange(regime.session);
  const { macroRisk, marketStress } = regime.scores;
  const labelName = regimeLabelFeature(regime);
  const names = [
    macroRisk.feature,
    marketStress.feature,
    labelName,
    ...(marketStress.coverageFeature === null ? [] : [marketStress.coverageFeature]),
  ];
  const history = useMarketHistory(names, range.window.start, range.window.end, POINTS);
  const episodes = useRegimeEpisodes();
  const named = (name: string | null) => history.data?.find((h) => h.name === name);
  const high = macroRisk.threshold ?? marketStress.threshold;
  const chart = toHistoryChart({
    series: [
      { id: 'macro', label: 'Macro risk', history: named(macroRisk.feature) },
      { id: 'stress', label: 'Market stress', history: named(marketStress.feature) },
    ],
    lanes: [regimeLane(named(labelName)), evidenceLane(named(marketStress.coverageFeature))],
    threshold: high === null ? null : { value: high, label: 'high' },
    episodes: episodes.data?.episodes ?? [],
    recessions: episodes.data?.recessions ?? [],
    window: range.window,
  });
  return (
    <Panel
      title="Scores through the cycles"
      description="Macro risk and market stress over the years, with the market's falls and the recessions behind them"
    >
      <Chart
        label="Macro risk and market stress scores, 0 to 100"
        {...chart}
        format={{ kind: 'number', digits: 0 }}
        height="lg"
        toolbar={<RegimeRangeControl session={regime.session} />}
        status={history.isError ? 'error' : history.isPending ? 'loading' : 'ready'}
        errorMessage="The score history failed to load."
        onRetry={() => void history.refetch()}
        emptyMessage="No scores are stored in this range."
      />
    </Panel>
  );
}

export function RegimeCycles() {
  const regime = useRegime();
  if (regime.isPending || regime.isError || regime.data === null) {
    const state = regime.isError ? 'error' : regime.isPending ? 'ready' : 'empty';
    return (
      <Panel
        title="Scores through the cycles"
        state={state}
        emptyMessage="No regime is stored yet, so there is no score history to show."
        errorMessage="The score history failed to load."
        onRetry={() => void regime.refetch()}
      >
        <Skeleton variant="table" rows={4} columns={2} label="Loading the score history" />
      </Panel>
    );
  }
  return <CyclesPanel regime={regime.data} />;
}
