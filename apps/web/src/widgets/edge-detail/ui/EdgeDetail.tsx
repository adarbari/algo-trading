/**
 * One edge: its thesis and what implements it, the canonical run's frozen-period figures per
 * variant and horizon through `OddsLine` (hit rate against the base rate, lift, independent
 * sessions), and every run the user sees with exploratory ones labelled EXPLORATORY and never
 * shown as figures. Each term carries its Guide button; the words are the server's.
 */
import {
  EmptyState,
  Heading,
  KeyValue,
  Mono,
  Panel,
  Stack,
  StatusBadge,
  Text,
  type KeyValueItem,
} from '@algotrade/ui';

import { unknownText } from '@/entities/availability';
import {
  statusLabel,
  statusTone,
  StoredOdds,
  useEdges,
  type Edge,
  type FrozenRow,
} from '@/entities/edge';
import { GuideHelp } from '@/features/guide-help';

const term = (id: string) => <GuideHelp entry={{ kind: 'term', id }} />;

function rowLabel(edge: Edge, row: FrozenRow): string {
  const prefix = row.edgeVariant === 'main' ? '' : `${row.edgeVariant} · `;
  const horizon = edge.horizons.length > 1 ? ` · ${String(row.horizonSessions)} sessions` : '';
  return `${prefix}${row.variant} (${row.role})${horizon}`;
}

function facts(edge: Edge): KeyValueItem[] {
  const items: KeyValueItem[] = [
    {
      id: 'status',
      label: 'Status',
      value: (
        <Stack direction="row" gap={1} align="center">
          <StatusBadge tone={statusTone(edge.status)}>{statusLabel(edge.status)}</StatusBadge>
          {term('edge_status')}
        </Stack>
      ),
    },
    {
      id: 'frozen',
      label: 'Frozen from',
      value: (
        <Stack direction="row" gap={1} align="center">
          <Mono>{edge.frozenFrom ?? 'none'}</Mono>
          {term('frozen_period')}
        </Stack>
      ),
    },
    { id: 'horizons', label: 'Horizons (sessions)', value: edge.horizons.join(', '), mono: true },
    { id: 'screeners', label: 'Screeners', value: edge.screeners.join(', ') || 'none', mono: true },
    { id: 'baselines', label: 'Baselines', value: edge.baselines.join(', ') || 'none', mono: true },
    { id: 'mechanism', label: 'Mechanism', value: edge.mechanism },
    { id: 'persistence', label: 'Why it lasts', value: edge.persistence },
    { id: 'schedule', label: 'Held', value: edge.schedule },
  ];
  if (edge.rejectionReason) {
    items.push({ id: 'rejected', label: 'Rejected because', value: edge.rejectionReason });
  }
  return items.filter((i) => i.value !== '');
}

function Frozen({ edge }: { edge: Edge }) {
  const run = edge.canonicalRun;
  return (
    <Stack gap={2}>
      <Stack direction="row" gap={1} align="center" wrap>
        <Heading level={3}>Frozen period</Heading>
        {term('base_rate')}
        {term('lift')}
        {term('independent_sessions')}
        {term('decile_spread')}
      </Stack>
      {!run ? (
        <Text size="sm" tone="muted">
          {unknownText(edge.canonicalNotRun)}
        </Text>
      ) : edge.frozenRows.length === 0 ? (
        <Text size="sm" tone="muted">
          No frozen rows stored
        </Text>
      ) : (
        edge.frozenRows.map((row) => (
          <Stack key={row.key} gap={0}>
            <Text size="sm" weight="medium">
              {rowLabel(edge, row)}
            </Text>
            <StoredOdds
              hitRate={row.hitRate}
              baseRate={row.baseRate}
              sessions={row.sessions}
              lift={row.lift}
              picks={row.picks}
              runLabel={`${run.runId} · ${run.rangeFrom ?? '…'} to ${run.rangeTo}`}
              info={term('hit_rate')}
            />
          </Stack>
        ))
      )}
    </Stack>
  );
}

function Runs({ edge }: { edge: Edge }) {
  if (edge.runs.length === 0) return null;
  return (
    <Stack gap={2}>
      <Stack direction="row" gap={1} align="center">
        <Heading level={3}>Runs</Heading>
        {term('trial_log')}
      </Stack>
      <Stack gap={1}>
        {edge.runs.map((run) => (
          <Stack key={run.runId} direction="row" gap={2} align="center" wrap>
            <Mono size="sm">{run.runId}</Mono>
            <Text
              size="sm"
              tone="muted"
            >{`split ${run.splitFrom ?? 'none'} · to ${run.rangeTo}`}</Text>
            {run.runId === edge.canonicalRun?.runId && (
              <StatusBadge tone="info">Canonical</StatusBadge>
            )}
            {run.exploratory && (
              <>
                <StatusBadge tone="warning">EXPLORATORY</StatusBadge>
                {term('exploratory')}
              </>
            )}
          </Stack>
        ))}
      </Stack>
    </Stack>
  );
}

export interface EdgeDetailProps {
  /** The chosen edge's id (from the URL), or null. */
  id: string | null;
}

export function EdgeDetail({ id }: EdgeDetailProps) {
  const edges = useEdges();
  const edge = id ? edges.data?.find((e) => e.id === id) : undefined;
  if (!id) return <EmptyState title="Choose an edge" icon="search" bordered />;
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
  return (
    <Panel title={edge.name} description={edge.thesis}>
      <Stack gap={4}>
        <KeyValue label={`${edge.name} facts`} layout="stacked" items={facts(edge)} />
        <Frozen edge={edge} />
        <Runs edge={edge} />
      </Stack>
    </Panel>
  );
}
