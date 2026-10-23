/**
 * A screener's evidence in the Screeners list (ADR 0053): the cell (the strongest edge's win rate
 * against its base rate, the lift, trades and holding period, that edge's name and status, and
 * how many more edges it is in) and the block that opens in place under the row, one record per
 * edge with its freeze date and a link to the edge. Only the server's frozen-period record is
 * read, never an exploratory one; a bare hit rate is never shown, and a screener with no usable
 * record says "No record yet" with the server's reason. The cell opens the block through an
 * `ExpandLink`; the Guide's help buttons come from the page (`help`), never text written here.
 */
import { Button, ExpandLink, formatValue, Skeleton, Stack, StatusBadge, Text } from '@algotrade/ui';
import { useState, type ReactNode } from 'react';

import { unknownText } from '@/entities/availability';

import { useTrackRecords } from '../api/track-records';
import { statusLabel, statusTone } from '../model/edges';
import {
  MIN_TRADES,
  screenerEvidence,
  type EdgeRecord,
  type RecordFigures,
} from '../model/track-records';

/** How many edges the opened block lists before "Show all". */
export const EDGES_SHOWN = 3;

const percent = (value: number, digits = 0) => formatValue(value, { kind: 'percent', digits }).text;
const lift = (value: number) => formatValue(value, { kind: 'delta', unit: 'points', digits: 0 });
const trades = (n: number) =>
  `${formatValue(n, { kind: 'number' }).text} ${n === 1 ? 'trade' : 'trades'}`;
const hold = (n: number) => `${String(n)}-session hold`;
const since = (date: string) => formatValue(date, { kind: 'date' }).text;

/** Why a record is not shown: the server's words, or how few trades there are. */
function pendingReason(edge: EdgeRecord): string {
  if (edge.state === 'few' && edge.figures) {
    return `Only ${trades(edge.figures.sessions)} since the freeze; ${String(MIN_TRADES)} are needed to read a win rate.`;
  }
  if (edge.state === 'partial')
    return 'The run is partial: its win rate or base rate is not stored.';
  return unknownText(edge.notRun);
}

function Lift({ figures }: { figures: RecordFigures }) {
  if (figures.liftPts === null) return null;
  const served = lift(figures.liftPts);
  const tone = served.tone === 'up' ? 'positive' : served.tone === 'down' ? 'negative' : 'neutral';
  return <StatusBadge tone={tone}>{served.text}</StatusBadge>;
}

function StatusChip({ status }: { status: string | null }) {
  return status ? <StatusBadge tone={statusTone(status)}>{statusLabel(status)}</StatusBadge> : null;
}

export interface ScreenerEvidenceCellProps {
  screenerId: string;
  /** Whether the block under the row is open. */
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ScreenerEvidenceCell({
  screenerId,
  open,
  onOpenChange,
}: ScreenerEvidenceCellProps) {
  const records = useTrackRecords(screenerId);
  if (records.isPending) return <Skeleton lines={1} label="Loading evidence…" />;
  if (records.isError) {
    return (
      <Text size="sm" tone="muted">
        The evidence failed to load
      </Text>
    );
  }
  const evidence = screenerEvidence(records.data);
  if (evidence.kind === 'no-edge') {
    return (
      <Text size="sm" tone="muted">
        Not part of an edge
      </Text>
    );
  }
  const more = evidence.edges.length - 1;
  const lead = evidence.kind === 'record' ? evidence.edges[0] : evidence.why;
  const chips = (
    <>
      {lead && <StatusBadge tone="neutral">{lead.edgeName}</StatusBadge>}
      {more > 0 && (
        <StatusBadge tone="neutral">{`+${String(more)} ${more === 1 ? 'edge' : 'edges'}`}</StatusBadge>
      )}
      <StatusChip status={lead?.edgeStatus ?? null} />
    </>
  );
  if (evidence.kind === 'record') {
    const first = evidence.headline;
    return (
      <Stack gap={1}>
        <Stack direction="row" gap={2} align="center" wrap>
          <ExpandLink open={open} onOpenChange={onOpenChange}>
            {`Win ${percent(first.hitRate)} vs ${percent(first.baseRate)} base`}
          </ExpandLink>
          <Lift figures={first} />
        </Stack>
        <Text size="xs" tone="muted">
          {`${trades(first.sessions)} · ${hold(first.horizonSessions)}`}
        </Text>
        <Stack direction="row" gap={1} align="center" wrap>
          {chips}
        </Stack>
      </Stack>
    );
  }
  return (
    <Stack gap={1}>
      {more > 0 ? (
        <ExpandLink open={open} onOpenChange={onOpenChange}>
          No record yet
        </ExpandLink>
      ) : (
        <Text size="sm" weight="medium">
          No record yet
        </Text>
      )}
      <Text size="xs" tone="muted">
        {pendingReason(evidence.why)}
      </Text>
      <Stack direction="row" gap={1} align="center" wrap>
        {chips}
      </Stack>
    </Stack>
  );
}

function EdgeBlock({
  edge,
  onOpenEdge,
}: {
  edge: EdgeRecord;
  onOpenEdge: (edgeId: string) => void;
}) {
  const { figures } = edge;
  return (
    <Stack as="li" gap={1}>
      <Stack direction="row" gap={2} align="center" wrap>
        <Text size="sm" weight="medium">
          {edge.edgeName}
        </Text>
        <StatusChip status={edge.edgeStatus} />
      </Stack>
      {edge.state === 'record' && figures ? (
        <Stack direction="row" gap={2} align="center" wrap>
          <Text size="sm">{`Win ${percent(figures.hitRate, 1)} vs ${percent(figures.baseRate, 1)} base`}</Text>
          <Lift figures={figures} />
          <Text size="xs" tone="muted">
            {`${trades(figures.sessions)} · ${hold(figures.horizonSessions)}`}
            {figures.frozenFrom ? ` · Frozen since ${since(figures.frozenFrom)}` : ''}
          </Text>
        </Stack>
      ) : (
        <Text size="xs" tone="muted">
          {`No record yet: ${pendingReason(edge)}`}
        </Text>
      )}
      <Stack direction="row">
        <Button
          size="sm"
          variant="ghost"
          iconEnd="chevron-right"
          aria-label={`Open edge ${edge.edgeName}`}
          onClick={() => {
            onOpenEdge(edge.edgeId);
          }}
        >
          Open edge
        </Button>
      </Stack>
    </Stack>
  );
}

export interface ScreenerEvidenceDetailProps {
  screenerId: string;
  /** Open an edge's evidence page. */
  onOpenEdge: (edgeId: string) => void;
  /** The Guide's "How to read a record" help button, made by the page. */
  help?: ReactNode;
}

/** The block under an opened row: one record per edge, at most EDGES_SHOWN until "Show all". */
export function ScreenerEvidenceDetail({
  screenerId,
  onOpenEdge,
  help,
}: ScreenerEvidenceDetailProps) {
  const records = useTrackRecords(screenerId);
  const [all, setAll] = useState(false);
  if (records.isPending || records.isError) return null;
  const evidence = screenerEvidence(records.data);
  if (evidence.kind === 'no-edge') return null;
  const hidden = all ? 0 : Math.max(0, evidence.edges.length - EDGES_SHOWN);
  const shown = hidden > 0 ? evidence.edges.slice(0, EDGES_SHOWN) : evidence.edges;
  return (
    <Stack gap={3}>
      <Stack direction="row" gap={1} align="center">
        <Text size="xs" tone="muted">
          How to read a record
        </Text>
        {help}
      </Stack>
      <Stack as="ul" gap={3} aria-label={`Edges of ${screenerId}`}>
        {shown.map((edge) => (
          <EdgeBlock key={edge.edgeId} edge={edge} onOpenEdge={onOpenEdge} />
        ))}
      </Stack>
      {hidden > 0 && (
        <Stack direction="row" gap={2} align="center">
          <Text size="xs" tone="muted">{`+${String(hidden)} more edges`}</Text>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              setAll(true);
            }}
          >
            Show all
          </Button>
        </Stack>
      )}
    </Stack>
  );
}
