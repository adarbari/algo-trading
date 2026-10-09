/**
 * A screener's track record as a compact card in its opened row (ADR 0053): hit rate against the
 * base rate, lift, sessions, horizon and edge from the server's frozen-period record (never an
 * exploratory run), with a link to the edge's evidence; the server's words when there is none.
 */
import { Button, formatValue, Stack, Text } from '@algotrade/ui';

import { unknownText } from '@/entities/availability';
import { recordFigures, useTrackRecords } from '@/entities/edge';

import { Facts } from './Facts';

const percent = (value: number) => formatValue(value, { kind: 'percent', digits: 1 }).text;
const lift = (value: number) => `${formatValue(value, { kind: 'number', digits: 2 }).text}×`;
const sessions = (n: number) => `${formatValue(n, { kind: 'number' }).text} sessions`;

export interface RecordCardProps {
  screenerId: string;
  /** Open the edge's evidence. */
  onOpenEdge: (edgeId: string) => void;
}

export function RecordCard({ screenerId, onOpenEdge }: RecordCardProps) {
  const records = useTrackRecords(screenerId);
  if (records.isPending) {
    return (
      <Text size="sm" tone="muted">
        Loading…
      </Text>
    );
  }
  const entries = records.data ?? [];
  const figures = recordFigures(entries);
  if (records.isError || !figures) {
    return (
      <Text size="sm" tone="muted">
        {records.isError
          ? 'Failed to load'
          : entries.length === 0
            ? 'No record yet'
            : unknownText(entries[0]?.notRun)}
      </Text>
    );
  }
  return (
    <Stack gap={2}>
      <Facts
        label="Track record"
        facts={[
          {
            id: 'hit',
            label: 'Hit rate',
            value: `${percent(figures.hitRate)} vs ${percent(figures.baseRate)} base`,
          },
          ...(figures.lift === null
            ? []
            : [{ id: 'lift', label: 'Lift', value: lift(figures.lift) }]),
          { id: 'sessions', label: 'Sessions', value: sessions(figures.sessions) },
          { id: 'horizon', label: 'Horizon', value: `${String(figures.horizonSessions)} sessions` },
          { id: 'edge', label: 'Edge', value: figures.edgeName },
        ]}
      />
      <Stack direction="row">
        <Button
          size="sm"
          variant="ghost"
          onClick={() => {
            onOpenEdge(figures.edgeId);
          }}
        >
          Edge evidence
        </Button>
      </Stack>
    </Stack>
  );
}
