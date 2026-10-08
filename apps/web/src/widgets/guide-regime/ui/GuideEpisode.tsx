/**
 * One reference market fall's Guide page: its name and kind, what caused it as the hero, the
 * facts (S&P 500 peak, trough, recovery, the S&P 500 and Nasdaq falls, any NBER recession), the
 * notes, and the indicators whose before-line is about it (each linked to its page). The text is
 * the server's, from `config/site/regime/episodes.toml` and the cards.
 */
import {
  EmptyState,
  ErrorState,
  Heading,
  KeyValue,
  Skeleton,
  Stack,
  Text,
  TextLink,
} from '@algotrade/ui';

import { episodeFacts, GuideProse, indicatorPath, useGuideEpisode } from '@/entities/guide';

export interface GuideEpisodeProps {
  /** The episode's slug in the URL. */
  slug: string;
}

export function GuideEpisode({ slug }: GuideEpisodeProps) {
  const query = useGuideEpisode(slug);
  if (query.isError) {
    return (
      <ErrorState title="The market fall failed to load." onRetry={() => void query.refetch()} />
    );
  }
  if (query.isPending)
    return <Skeleton variant="rect" height="lg" label="Loading the market fall" />;
  const detail = query.data;
  if (!detail) {
    return (
      <EmptyState
        bordered
        title="No such market fall"
        description={`The Guide has no market fall called ${slug}.`}
      />
    );
  }
  const { episode } = detail;
  return (
    <Stack gap={6}>
      <Stack gap={2} as="section" aria-label="Market fall">
        <Text size="sm" tone="muted">
          {episode.kind === 'recession' ? 'Recession bear market' : 'Shock or re-rating'}
        </Text>
        <Heading level={1} size="3xl">
          {episode.name}
        </Heading>
        <Text as="p" size="xl">
          <GuideProse prose={detail.cause} size="xl" />
        </Text>
      </Stack>
      <Stack gap={2} as="section" aria-label="The fall">
        <Heading level={2}>The fall</Heading>
        <KeyValue items={episodeFacts(episode)} label={`${episode.name}: the fall`} />
      </Stack>
      {detail.notes.segments.length > 0 && (
        <Stack gap={2} as="section" aria-label="Notes">
          <Heading level={2}>Notes</Heading>
          <Text as="p">
            <GuideProse prose={detail.notes} />
          </Text>
        </Stack>
      )}
      {detail.indicators.length > 0 && (
        <Stack gap={2} as="section" aria-label="What the warning signs did before it">
          <Heading level={2}>What the warning signs did before it</Heading>
          <Stack as="ul" gap={2}>
            {detail.indicators.map((i) => (
              <Stack as="li" key={i.key} gap={0}>
                <TextLink href={indicatorPath(i.key)}>{i.plainName}</TextLink>
                <Text size="sm" tone="secondary">
                  <GuideProse prose={i.line} tone="secondary" size="sm" />
                </Text>
              </Stack>
            ))}
          </Stack>
        </Stack>
      )}
    </Stack>
  );
}
