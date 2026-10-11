/**
 * An edge's live state as a badge in a page header (ADR 0064 decision 9): shown only when the
 * edge is below its usual range (the state, label and sentence are the server's), with the Guide
 * term that explains it beside it. Nothing while loading, when the edge has no live state or
 * when it is not below range.
 */
import { StatusBadge } from '@algotrade/ui';

import { useEdgeLiveStates } from '../api/paper';
import { recordLabel, recordTone } from '../model/paper';

export interface EdgeLiveBadgeProps {
  edgeId: string;
}

export function EdgeLiveBadge({ edgeId }: EdgeLiveBadgeProps) {
  const states = useEdgeLiveStates();
  const live = states.data?.find((s) => s.edgeId === edgeId);
  if (live?.state !== 'below') return null;
  return <StatusBadge tone={recordTone(live.state)}>{recordLabel(live.state)}</StatusBadge>;
}
