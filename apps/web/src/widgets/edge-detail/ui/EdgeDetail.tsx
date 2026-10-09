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
  Chip,
  EmptyState,
  formatValue,
  Grid,
  Heading,
  Panel,
  Stack,
  StatusBadge,
  Text,
} from '@algotrade/ui';
import { lazy, Suspense } from 'react';

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
import { lazyPage } from '@/shared/lib/lazy';

import { EdgeDefinition } from './EdgeDefinition';
import { EdgeDetails } from './EdgeDetails';
import { EdgeFigures } from './EdgeFigures';
import { EdgeLive } from './EdgeLive';
import { EdgeYears } from './EdgeYears';

/** The decile bars and the robustness histogram load on demand: their own chunk, so the page's first paint stays small. */
const EdgeDeciles = lazy(() => import('./EdgeDeciles').then((m) => ({ default: m.EdgeDeciles })));
const EdgeRobustness = lazy(() =>
  import('./EdgeRobustness').then((m) => ({ default: m.EdgeRobustness })),
);
// A copy's comparison is for the user's own edges only: its chunk loads when there is one.
const EdgeCompare = lazyPage(() => import('./EdgeCompare'), 'EdgeCompare');

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
                {`${edge.mine ? `Your edge · extends ${edge.extends ?? 'nothing'}` : 'Site edge'} · ${statusLabel(edge.status)}`}
              </Text>
              <GuideHelp entry={{ kind: 'term', id: 'edge_copy' }} />
              <GuideHelp entry={{ kind: 'term', id: 'edge_status' }} />
              <StatusBadge tone={stateTone(edge.state)}>{stateLabel(edge.state)}</StatusBadge>
              <GuideHelp entry={{ kind: 'term', id: 'edge_state' }} />
              {edge.canonicalRun && (
                <>
                  <Text size="sm" tone="secondary">
                    {`Last backtest ${formatValue(edge.canonicalRun.knowledgeTs, { kind: 'date', style: 'day' }).text} (official result)`}
                  </Text>
                  <GuideHelp entry={{ kind: 'term', id: 'official_result' }} />
                </>
              )}
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
      <Grid columns={2} gap={4} collapse="lg" align="start">
        <Suspense fallback={<Panel title="Top vs bottom decile" state="loading" />}>
          <EdgeDeciles deciles={v.deciles} />
        </Suspense>
        <Suspense fallback={<Panel title="Robustness" state="loading" />}>
          <EdgeRobustness robustness={v.robustness} />
        </Suspense>
      </Grid>
      {edge.mine && (
        <Suspense
          fallback={<Panel title="Compare versions" state="loading" loadingLabel="Loading…" />}
        >
          <EdgeCompare edgeId={edge.id} />
        </Suspense>
      )}
      <EdgeYears years={v.years} />
      <EdgeLive edgeId={edge.id} />
      <EdgeDefinition edge={edge} />
      <EdgeDetails edge={edge} />
    </Stack>
  );
}
