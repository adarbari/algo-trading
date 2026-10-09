/**
 * "How early did we know": for each reference market fall, when each warning sign and the
 * screener gate flagged, in sessions from the peak (negative: before it). An overview timeline
 * has one row per fall with a marker per signal (fast and slow by colour, the gate a diamond,
 * a late one hollow); a fall opens in place to a bar per signal from flagged to cleared, with the
 * server's state (late, never fired, unknown with its reason) beside it. The signals come in one
 * request for the whole section; a help button opens the Guide entry. Data, empty and error states.
 */
import {
  ExpandableRow,
  Legend,
  Panel,
  Skeleton,
  Stack,
  Text,
  Timeline,
  formatValue,
  timelineDomain,
} from '@algotrade/ui';
import { useMemo, useState } from 'react';

import {
  detailRows,
  overviewRow,
  SIGNAL_KEY,
  useRegime,
  useRegimeEpisodes,
  useRegimeSignals,
  type EpisodeSignals,
  type RegimeEpisode,
  type RegimeIndicator,
} from '@/entities/regime';
import { GuideHelp } from '@/features/guide-help';

const PEAK = { at: 0, label: 'the market peak' };
const AXIS = 'Sessions from the peak';

function Falls({
  episodes,
  signals,
  indicators,
}: {
  episodes: readonly RegimeEpisode[];
  signals: ReadonlyMap<string, EpisodeSignals | null>;
  indicators: readonly RegimeIndicator[];
}) {
  const [open, setOpen] = useState<string | null>(null);
  const { overview, details, domain } = useMemo(() => {
    const overviewRows = episodes.map((e) =>
      overviewRow(e, signals.get(e.key) ?? null, indicators),
    );
    const detailByKey = new Map(
      episodes.flatMap((e) => {
        const found = signals.get(e.key);
        return found ? [[e.key, detailRows(found, indicators)] as const] : [];
      }),
    );
    return {
      overview: overviewRows,
      details: detailByKey,
      domain: timelineDomain([overviewRows, ...detailByKey.values()], PEAK.at),
    };
  }, [episodes, signals, indicators]);
  return (
    <Stack gap={3}>
      <Legend label="Signal kinds" items={[...SIGNAL_KEY]} />
      <Timeline
        label="When each warning sign first flagged, by market fall"
        rows={overview}
        domain={domain}
        reference={PEAK}
        axisLabel={AXIS}
        size="sm"
      />
      <Stack as="ul" gap={0}>
        {episodes.map((episode) => {
          const rows = details.get(episode.key);
          return (
            <Stack as="li" key={episode.key}>
              <ExpandableRow
                title={episode.name}
                secondary={
                  <Text size="sm" tone="secondary">
                    {`Peak ${formatValue(episode.peak, { kind: 'date' }).text}`}
                  </Text>
                }
                essential={formatValue(episode.spxDrawdown, { kind: 'percent', digits: 0 }).text}
                open={open === episode.key}
                onOpenChange={(next) => {
                  setOpen(next ? episode.key : null);
                }}
              >
                {rows === undefined ? (
                  <Text size="sm" tone="muted">
                    No signal timing is stored for this fall.
                  </Text>
                ) : (
                  <Timeline
                    label={`Signals around ${episode.name}`}
                    rows={rows}
                    domain={domain}
                    reference={PEAK}
                    axisLabel={AXIS}
                  />
                )}
              </ExpandableRow>
            </Stack>
          );
        })}
      </Stack>
    </Stack>
  );
}

export function RegimeTiming() {
  const regime = useRegime();
  const episodes = useRegimeEpisodes();
  const signals = useRegimeSignals();
  const failed = regime.isError || episodes.isError || signals.isError;
  const loading = regime.isPending || episodes.isPending || signals.isPending;
  const list = episodes.data?.episodes ?? [];
  return (
    <Panel
      title="How early did we know"
      description="When each warning sign and the screener gate flagged around each market fall"
      actions={<GuideHelp entry={{ kind: 'start', id: 'reading_recession_signals' }} />}
      state={failed ? 'error' : loading ? 'ready' : list.length === 0 ? 'empty' : 'ready'}
      emptyMessage="No market falls are stored for this session."
      errorMessage="The signal timing failed to load."
      onRetry={() => {
        void regime.refetch();
        void episodes.refetch();
        void signals.refetch();
      }}
    >
      {loading && !failed && (
        <Skeleton variant="table" rows={5} columns={2} label="Loading the signal timing" />
      )}
      {!loading && !failed && list.length > 0 && (
        <Falls episodes={list} signals={signals.data} indicators={regime.data?.indicators ?? []} />
      )}
    </Panel>
  );
}
