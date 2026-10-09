/**
 * One edge's page: its name, verdict (with the server's reason) and status, the Run backtest
 * button, the headline sentence, the out-of-sample figures, year by year, how the edge is
 * defined, why it should last with its sources, and the details (tests, backtests, figures, the
 * user's own split). Each term carries its Guide button; every word and number is the server's.
 */
import { Button, Chip, EmptyState, Heading, Panel, Stack, StatusBadge, Text } from '@algotrade/ui';

import {
  labelText,
  stateLabel,
  stateTone,
  statusLabel,
  useEdges,
  verdictLabel,
  verdictTone,
} from '@/entities/edge';
import { EdgeActions } from '@/features/edge-follow';
import { RunEvaluation } from '@/features/edge-evaluation';
import { GuideHelp } from '@/features/guide-help';

import { EdgeCompare } from './EdgeCompare';
import { EdgeDefinition } from './EdgeDefinition';
import { EdgeDetails } from './EdgeDetails';
import { EdgeFigures } from './EdgeFigures';
import { EdgeYears } from './EdgeYears';

export interface EdgeDetailProps {
  /** The chosen edge's id (from the URL). */
  id: string;
  /** Back to the edges list. */
  onBack: () => void;
  /** Open another edge's page (a clone was made). */
  onOpen: (id: string) => void;
}

export function EdgeDetail({ id, onBack, onOpen }: EdgeDetailProps) {
  const edges = useEdges();
  const edge = edges.data?.find((e) => e.id === id);
  if (edges.isPending) return <Panel title="Edge" state="loading" loadingLabel="Loading edge…" />;
  if (edges.isError && !edges.data) {
    return (
      <Panel
        title="Edge"
        state="error"
        errorMessage="The edge failed to load."
        onRetry={() => void edges.refetch()}
      />
    );
  }
  if (!edge) return <EmptyState title={`No edge ${id}`} bordered />;
  const v = edge.verdict;
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
              <GuideHelp entry={{ kind: 'term', id: 'verdict' }} />
              <Text size="sm" tone="secondary">
                {edge.mine ? `Your edge · extends ${edge.extends ?? 'nothing'}` : 'Site edge'}
              </Text>
              <GuideHelp entry={{ kind: 'term', id: 'edge_copy' }} />
              <Text size="sm" tone="secondary">
                {statusLabel(edge.status)}
              </Text>
              <GuideHelp entry={{ kind: 'term', id: 'edge_status' }} />
              <StatusBadge tone={stateTone(edge.state)}>{stateLabel(edge.state)}</StatusBadge>
              <GuideHelp entry={{ kind: 'term', id: 'edge_state' }} />
            </Stack>
            {edge.labels.length > 0 && (
              <Stack direction="row" gap={1} align="center" wrap>
                {edge.labels.map((label) => (
                  <Chip key={label} label={labelText(label)} />
                ))}
                <GuideHelp entry={{ kind: 'term', id: 'edge_labels' }} />
              </Stack>
            )}
          </Stack>
          <Stack gap={2} align="end">
            <RunEvaluation edgeId={edge.id} />
            <Stack direction="row" gap={1} align="center">
              <EdgeActions edge={edge} onCloned={onOpen} />
              <GuideHelp entry={{ kind: 'term', id: 'follow_edge' }} />
              {edge.oosHidden && <GuideHelp entry={{ kind: 'term', id: 'show_out_of_sample' }} />}
            </Stack>
          </Stack>
        </Stack>
        <Text size="base">{v.headline}</Text>
        {edge.rejectionReason && (
          <Text size="sm" tone="muted">
            {edge.rejectionReason}
          </Text>
        )}
      </Stack>
      <EdgeFigures verdict={v} />
      {edge.compare && <EdgeCompare compare={edge.compare} />}
      <EdgeYears years={v.years} />
      <EdgeDefinition edge={edge} />
      <EdgeDetails edge={edge} />
    </Stack>
  );
}
