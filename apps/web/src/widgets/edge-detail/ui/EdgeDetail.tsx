/**
 * One edge's page: its name, verdict (with the server's reason), whose edge it is, its status and
 * the date of the official result, the Run backtest button, the headline sentence, the
 * out-of-sample figures, the decile bars beside the robustness against random picks, year by
 * year, how the edge is defined, why it should last with its sources, and the details (tests,
 * backtests, figures, the user's own split). Each term carries its Guide button; every word and
 * number is the server's.
 */
import {
  Button,
  EmptyState,
  formatValue,
  Grid,
  Heading,
  Panel,
  Stack,
  StatusBadge,
  Text,
} from '@algotrade/ui';

import { statusLabel, useEdges, verdictLabel, verdictTone } from '@/entities/edge';
import { RunEvaluation } from '@/features/edge-evaluation';
import { GuideHelp } from '@/features/guide-help';

import { EdgeDefinition } from './EdgeDefinition';
import { EdgeDeciles } from './EdgeDeciles';
import { EdgeDetails } from './EdgeDetails';
import { EdgeFigures } from './EdgeFigures';
import { EdgeRobustness } from './EdgeRobustness';
import { EdgeYears } from './EdgeYears';

export interface EdgeDetailProps {
  /** The chosen edge's id (from the URL). */
  id: string;
  /** Back to the edges list. */
  onBack: () => void;
}

export function EdgeDetail({ id, onBack }: EdgeDetailProps) {
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
                {`${edge.mine ? 'Your edge' : 'Site edge'} · ${statusLabel(edge.status)}`}
              </Text>
              <GuideHelp entry={{ kind: 'term', id: 'edge_status' }} />
              {edge.canonicalRun && (
                <>
                  <Text size="sm" tone="secondary">
                    {`Last backtest ${formatValue(edge.canonicalRun.knowledgeTs, { kind: 'date', style: 'day' }).text} (official result)`}
                  </Text>
                  <GuideHelp entry={{ kind: 'term', id: 'official_result' }} />
                </>
              )}
            </Stack>
          </Stack>
          <RunEvaluation edgeId={edge.id} />
        </Stack>
        <Text size="base">{v.headline}</Text>
        {edge.rejectionReason && (
          <Text size="sm" tone="muted">
            {edge.rejectionReason}
          </Text>
        )}
      </Stack>
      <EdgeFigures verdict={v} />
      <Grid columns={2} gap={4} collapse="lg" align="start">
        <EdgeDeciles deciles={v.deciles} />
        <EdgeRobustness robustness={v.robustness} />
      </Grid>
      <EdgeYears years={v.years} />
      <EdgeDefinition edge={edge} />
      <EdgeDetails edge={edge} />
    </Stack>
  );
}
