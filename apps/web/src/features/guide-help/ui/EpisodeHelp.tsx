/**
 * A reference market fall's help: its name and kind, the facts (peak, trough, recovery, how far
 * the S&P 500 and the Nasdaq fell, any NBER recession) and what caused it.
 * The facts are the episode's (`config/site/regime/episodes.toml`); nothing is written here.
 */
import { HelpLead, HelpSection, KeyValue } from '@algotrade/ui';

import { episodeFacts, GuideProse, useGuideEpisode } from '@/entities/guide';

import { HelpShell } from './HelpShell';

export function EpisodeHelp({ episodeKey }: { episodeKey: string }) {
  const query = useGuideEpisode(episodeKey);
  const detail = query.data;
  const episode = detail?.episode;
  return (
    <HelpShell
      entry={{ kind: 'episode', id: episodeKey }}
      label={`About ${episode?.name ?? 'this market fall'}`}
      title={episode?.name ?? 'Market fall'}
      eyebrow="Market fall"
      {...(episode
        ? { meta: episode.kind === 'recession' ? 'Recession bear market' : 'Shock or re-rating' }
        : {})}
      state={query.isPending ? 'pending' : query.isError ? 'error' : !episode ? 'missing' : 'ready'}
      missingText="The Guide has no entry for this market fall yet."
      onRetry={() => {
        void query.refetch();
      }}
      retrying={query.isFetching}
    >
      {detail && episode && (
        <>
          <HelpSection title="The fall">
            <KeyValue items={episodeFacts(episode)} label={`${episode.name}: the fall`} />
          </HelpSection>
          <HelpSection title="What caused it">
            <HelpLead>
              <GuideProse prose={detail.cause} />
            </HelpLead>
          </HelpSection>
        </>
      )}
    </HelpShell>
  );
}
