/**
 * The evaluation line under an edge's verdict: which evaluation the verdict rests on and whether
 * it is current, stale or being re-evaluated. The state and the sentence are the server's (the
 * browser derives nothing); each state has its Guide entry. An admin also gets the full run id as a link
 * to the Edge runs page (the server serves it to admins only). It wraps at phone width.
 */
import { Stack, StatusBadge, Text, TextLink } from '@algotrade/ui';

import { provenanceLabel, provenanceTerm, provenanceTone, type Edge } from '@/entities/edge';
import { termHelp } from '@/features/guide-help';

export interface EdgeProvenanceProps {
  /** The server's provenance of the verdict's evaluation. */
  provenance: NonNullable<Edge['provenance']>;
}

export function EdgeProvenance({ provenance }: EdgeProvenanceProps) {
  const { state, line, runId } = provenance;
  return (
    <Stack direction="row" gap={2} align="center" wrap>
      <StatusBadge tone={provenanceTone(state)}>{provenanceLabel(state)}</StatusBadge>
      {termHelp(provenanceTerm(state))}
      <Text size="sm" tone="secondary">
        {line}
      </Text>
      {termHelp('edge_provenance')}
      {runId && (
        <TextLink href={`/admin/harness-runs?run=${encodeURIComponent(runId)}`} size="sm" mono>
          {runId}
        </TextLink>
      )}
    </Stack>
  );
}
