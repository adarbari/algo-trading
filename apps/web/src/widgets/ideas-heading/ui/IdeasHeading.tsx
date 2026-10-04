/**
 * "Ideas for Fri 2 Oct": the session the stored screens ran on; plain "Ideas" while loading or
 * when the ideas are unavailable.
 */
import { formatValue, Heading } from '@algotrade/ui';

import { useIdeas } from '@/entities/idea';

export function IdeasHeading() {
  const ideas = useIdeas();
  const session = ideas.data?.session;
  return (
    <Heading level={1}>
      {session
        ? `Ideas for ${formatValue(session, { kind: 'date', style: 'weekday' }).text}`
        : 'Ideas'}
    </Heading>
  );
}
