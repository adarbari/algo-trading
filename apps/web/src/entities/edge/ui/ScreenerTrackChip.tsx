/**
 * A screener's track-record chip (Screeners list): the state of the first edge that lists it,
 * with "+N" for the others; nothing when no edge lists it or its edge is retired, rejected or
 * blocked. The chip never reads an exploratory run (the server sends only the frozen record).
 */
import { Stack, Text, TrackRecordChip } from '@algotrade/ui';

import { useTrackRecords } from '../api/track-records';
import { chipOf } from '../model/track-records';

export function ScreenerTrackChip({ screenerId }: { screenerId: string }) {
  const records = useTrackRecords(screenerId);
  const chip = chipOf(records.data ?? []);
  if (!chip) return null;
  return (
    <Stack direction="row" gap={1} align="center">
      <TrackRecordChip
        status={chip.status}
        {...(chip.sessions === undefined ? {} : { sessions: chip.sessions })}
      />
      {chip.more > 0 && <Text size="xs" tone="muted">{`+${String(chip.more)}`}</Text>}
    </Stack>
  );
}
