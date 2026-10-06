/**
 * The reading list: every link the indicator cards cite, once each, with the cards that cite
 * it. The cards are the only source (the page never invents a link). Data, empty and error
 * states.
 */
import { ExternalLink, Panel, Skeleton, Stack, Text } from '@algotrade/ui';

import { readingList, useRegime } from '@/entities/regime';

export function ReadingList() {
  const regime = useRegime();
  const links = regime.data ? readingList(regime.data) : [];
  const state = regime.isError
    ? 'error'
    : regime.isPending
      ? 'ready'
      : links.length === 0
        ? 'empty'
        : 'ready';
  return (
    <Panel
      title="Reading list"
      description="Where the warning signs come from, and how to judge them"
      state={state}
      emptyMessage="No indicator card cites a link yet."
      errorMessage="The reading list failed to load."
      onRetry={() => void regime.refetch()}
    >
      {regime.isPending && <Skeleton lines={4} label="Loading the reading list" />}
      <Stack as="ul" gap={2}>
        {links.map((link) => (
          <Stack as="li" key={link.url} gap={0}>
            <ExternalLink href={link.url}>{link.title}</ExternalLink>
            <Text size="sm" tone="muted">{`Cited by: ${link.cards.join(', ')}`}</Text>
          </Stack>
        ))}
      </Stack>
    </Panel>
  );
}
