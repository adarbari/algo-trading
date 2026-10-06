/**
 * The reference market falls as a table (RG7): name, peak, trough, depth, recovery and whether
 * the NBER dated a recession in it, newest first. Choosing a row (click or Enter) sets the
 * window of every history chart on the page to a year before its peak through six months after
 * its recovery. Data, empty and error states.
 */
import { DataTable, Panel } from '@algotrade/ui';

import { episodeWindow, useRegime, useRegimeEpisodes, type RegimeEpisode } from '@/entities/regime';
import { useRegimeRange } from '@/features/regime-range';

import { episodeColumns } from '../model/columns';

const COLUMNS = episodeColumns();

function EpisodesTable({
  session,
  episodes,
}: {
  session: string;
  episodes: readonly RegimeEpisode[];
}) {
  const range = useRegimeRange(session);
  return (
    <DataTable
      label="Market falls"
      columns={COLUMNS}
      rows={episodes}
      getRowId={(episode) => episode.key}
      defaultSort={{ columnId: 'peak', direction: 'desc' }}
      visibleRows={12}
      emptyMessage="No market falls are known for this session."
      onRowActivate={(episode) => {
        range.setWindow(episode.name, episodeWindow(episode, session));
      }}
    />
  );
}

export function RegimeEpisodes() {
  const regime = useRegime();
  const episodes = useRegimeEpisodes();
  const session = regime.data?.session;
  const state = regime.isError || episodes.isError ? 'error' : undefined;
  const loading = regime.isPending || episodes.isPending;
  return (
    <Panel
      title="Market falls we compare with"
      description="Choose one to chart its fall, recovery and the recessions around it"
      flush
      state={state ?? (loading ? 'loading' : session === undefined ? 'empty' : 'ready')}
      loadingLabel="Loading the market falls"
      emptyMessage="No market falls are stored for this session."
      errorMessage="The market falls failed to load."
      onRetry={() => {
        void regime.refetch();
        void episodes.refetch();
      }}
    >
      {session !== undefined && episodes.data !== undefined && (
        <EpisodesTable session={session} episodes={episodes.data.episodes} />
      )}
    </Panel>
  );
}
