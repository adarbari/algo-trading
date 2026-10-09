/**
 * A screener's track record in a table cell of the Screeners list (ADR 0053): hit rate against
 * the base rate, then lift, sessions and horizon; "No record yet" without one. Only the server's
 * frozen-period record is read, never an exploratory one. `ScreenerEdgeName` is the edge a
 * screener implements, or that it is part of none.
 */
import { formatValue, Skeleton, Text } from '@algotrade/ui';

import { useTrackRecords } from '../api/track-records';
import { recordFigures, type RecordFigures } from '../model/track-records';

const percent = (value: number) => formatValue(value, { kind: 'percent', digits: 0 }).text;
const lift = (value: number) => `${formatValue(value, { kind: 'number', digits: 2 }).text}×`;
const sessions = (n: number) => `${formatValue(n, { kind: 'number' }).text} sessions`;

export interface ScreenerRecordProps {
  screenerId: string;
}

/** The edge name under a screener's name, or that it is part of none. */
export function ScreenerEdgeName({ screenerId }: { screenerId: string }) {
  const records = useTrackRecords(screenerId);
  const first = records.data?.[0];
  if (records.isPending) return null;
  return (
    <Text size="xs" tone="muted">
      {first ? `Edge: ${first.edgeName}` : 'Not part of an edge'}
    </Text>
  );
}

function Cell({ figures }: { figures: RecordFigures }) {
  return (
    <>
      <Text size="sm" weight="medium">
        {`${percent(figures.hitRate)} vs ${percent(figures.baseRate)} base`}
      </Text>
      <Text size="xs" tone="muted">
        {[
          figures.lift === null ? null : `lift ${lift(figures.lift)}`,
          sessions(figures.sessions),
          `${String(figures.horizonSessions)}d`,
        ]
          .filter(Boolean)
          .join(' · ')}
      </Text>
    </>
  );
}

export function ScreenerRecord({ screenerId }: ScreenerRecordProps) {
  const records = useTrackRecords(screenerId);
  if (records.isPending) return <Skeleton lines={1} label="Loading track record…" />;
  const figures = recordFigures(records.data ?? []);
  if (records.isError || !figures) {
    return (
      <Text size="sm" tone="muted">
        No record yet
      </Text>
    );
  }
  return <Cell figures={figures} />;
}
