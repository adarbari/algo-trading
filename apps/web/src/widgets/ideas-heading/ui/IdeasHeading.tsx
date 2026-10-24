/**
 * "Ideas for Fri 2 Oct": the session the stored screens ran on; plain "Ideas" while loading or
 * when the ideas are unavailable. Under it, one chip per screener with its state for the session.
 */
import { formatValue, Heading, Stack } from '@algotrade/ui';

import { useIdeas } from '@/entities/idea';

import { ScreenerChips } from './ScreenerChips';

export function IdeasHeading() {
  const ideas = useIdeas();
  const session = ideas.data?.session;
  return (
    <Stack gap={2}>
      <Heading level={1}>
        {session
          ? `Ideas for ${formatValue(session, { kind: 'date', style: 'weekday' }).text}`
          : 'Ideas'}
      </Heading>
      <ScreenerChips screeners={ideas.data?.screeners ?? []} />
    </Stack>
  );
}
