/**
 * A screener's track record as one line (ADR 0053), in the Edge Builder's screens step: win rate against
 * the base rate, then trades and holding period (the lift waits for a served points field); "No record yet" without one. Only the server's
 * frozen-period record is read, never an exploratory one. The Screeners list has its own evidence
 * cell (`ScreenerEvidence`).
 */
import { formatValue, Skeleton, Text } from '@algotrade/ui';

import { useTrackRecords } from '../api/track-records';
import { recordFigures, type RecordFigures } from '../model/track-records';

const percent = (value: number) => formatValue(value, { kind: 'percent', digits: 0 }).text;
const trades = (n: number) => `${formatValue(n, { kind: 'number' }).text} trades`;

export interface ScreenerRecordProps {
  screenerId: string;
}

function Cell({ figures }: { figures: RecordFigures }) {
  return (
    <>
      <Text size="sm" weight="medium">
        {`Win rate ${percent(figures.hitRate)} vs ${percent(figures.baseRate)} base`}
      </Text>
      <Text size="xs" tone="muted">
        {`${trades(figures.sessions)} · ${String(figures.horizonSessions)}-session hold`}
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
