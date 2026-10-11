/**
 * An edge's live state as a badge in a page header (ADR 0064 decision 9): shown only when the
 * edge is below its usual range (the state and label are the server's), followed by `help`, the
 * caller's Guide button for the state. Nothing while loading, when the edge has no live state or
 * when it is not below range.
 */
import { Stack, StatusBadge } from '@algotrade/ui';
import type { ReactNode } from 'react';

import { useEdgeLiveStates } from '../api/paper';
import { recordLabel, recordTone } from '../model/paper';

export interface EdgeLiveBadgeProps {
  edgeId: string;
  /** The Guide button that explains the state, shown with the badge only. */
  help?: ReactNode;
}

export function EdgeLiveBadge({ edgeId, help }: EdgeLiveBadgeProps) {
  const states = useEdgeLiveStates();
  const live = states.data?.find((s) => s.edgeId === edgeId);
  if (live?.state !== 'below') return null;
  return (
    <Stack direction="row" gap={1} align="center">
      <StatusBadge tone={recordTone(live.state)}>{recordLabel(live.state)}</StatusBadge>
      {help}
    </Stack>
  );
}
