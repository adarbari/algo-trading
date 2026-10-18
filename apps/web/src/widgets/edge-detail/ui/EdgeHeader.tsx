/**
 * The head of an edge's page: its name, verdict (with the server's reason), whose edge it is, its
 * status and live state, the date of the official result and the data it read, the actions, the
 * headline sentence, and what would change the verdict (the evidence collected against the
 * evidence needed, and the checks that the result is real). The first paint of the page: it
 * reads only the edges the page already holds. Each term carries its Guide button; every word and
 * number is the server's.
 */
import { Button, Chip, formatValue, Heading, Stack, StatusBadge, Text } from '@algotrade/ui';

import {
  EdgeLiveBadge,
  labelText,
  sideLabel,
  stateLabel,
  stateTone,
  statusLabel,
  verdictLabel,
  verdictTone,
  type Edge,
} from '@/entities/edge';
import { RunEvaluation } from '@/features/edge-evaluation';
import { EdgeActions } from '@/features/edge-follow';
import { termHelp } from '@/features/guide-help';

import { EdgeOutlook } from './EdgeOutlook';

export interface EdgeHeaderProps {
  /** The chosen edge. */
  edge: Edge;
  /** Back to the edges list. */
  onBack: () => void;
  /** Open the builder on one of the user's edges (a copy was made, or Edit). */
  onEdit: (id: string) => void;
}

export function EdgeHeader({ edge, onBack, onEdit }: EdgeHeaderProps) {
  const v = edge.verdict;
  const dataTo = edge.runs.find((run) => run.runId === edge.canonicalRun?.runId)?.rangeTo;
  return (
    <Stack gap={4}>
      <Stack gap={2}>
        <Stack direction="row">
          <Button size="sm" variant="ghost" onClick={onBack}>
            ← Edges
          </Button>
        </Stack>
        <Stack direction="row" gap={3} align="center" justify="between" wrap>
          <Stack gap={1}>
            <Heading level={1}>{edge.name}</Heading>
            <Stack direction="row" gap={2} align="center" wrap>
              <StatusBadge tone={verdictTone(v.verdict)}>{verdictLabel(v.verdict)}</StatusBadge>
              {termHelp('verdict')}
              <Text size="sm" tone="secondary">
                {`${edge.mine ? `Your edge · extends ${edge.extends ?? 'nothing'}` : 'Site edge'} · ${statusLabel(edge.status)}`}
              </Text>
              {termHelp('edge_copy')}
              {termHelp('edge_status')}
              <StatusBadge tone={stateTone(edge.state)}>{stateLabel(edge.state)}</StatusBadge>
              {termHelp('edge_state')}
              <EdgeLiveBadge edgeId={edge.id} help={termHelp('live_state')} />
              {edge.canonicalRun && (
                <>
                  <Text size="sm" tone="secondary">
                    {`Official result ${formatValue(edge.canonicalRun.knowledgeTs, { kind: 'date', style: 'day' }).text}`}
                  </Text>
                  {termHelp('official_result')}
                  {dataTo && (
                    <Text size="sm" tone="secondary">
                      {`data to ${formatValue(dataTo, { kind: 'date', style: 'day' }).text}`}
                    </Text>
                  )}
                </>
              )}
              {v.basis && (
                <>
                  <Text size="sm" tone="secondary">
                    {v.basis}
                  </Text>
                  {termHelp('verdict_basis')}
                </>
              )}
              {sideLabel(v.side) && (
                <>
                  <Chip label={sideLabel(v.side) ?? ''} />
                  {termHelp(v.side === 'short' ? 'side_short' : 'side_long_short')}
                </>
              )}
            </Stack>
            {edge.labels.length > 0 && (
              <Stack direction="row" gap={1} align="center" wrap>
                {edge.labels.map((label) => (
                  <Chip key={label} label={labelText(label)} />
                ))}
                {termHelp('edge_labels')}
              </Stack>
            )}
          </Stack>
          <Stack gap={2} align="end">
            <Stack direction="row" gap={1} align="center">
              <RunEvaluation edgeId={edge.id} />
              {termHelp('run_backtest')}
            </Stack>
            <Stack direction="row" gap={1} align="center">
              <EdgeActions edge={edge} onEdit={onEdit} />
              {termHelp('follow_edge')}
              {edge.oosHidden && termHelp('show_out_of_sample')}
            </Stack>
          </Stack>
        </Stack>
        <Text size="base">{v.headline}</Text>
        {v.basisWhy && (
          <Text size="sm" tone="muted">
            {v.basisWhy}
          </Text>
        )}
        {edge.rejectionReason && (
          <Text size="sm" tone="muted">
            {edge.rejectionReason}
          </Text>
        )}
      </Stack>
      {v.evidence && <EdgeOutlook evidence={v.evidence} />}
    </Stack>
  );
}
