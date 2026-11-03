/**
 * The parts of the calendar the session does not know (the API's gap lines), said once above
 * each view in one banner with the Guide's UNKNOWN entry; nothing when every part is known.
 */
import { Banner, Stack, Text } from '@algotrade/ui';

import { termHelp } from '@/features/guide-help';

export function GapNotes({ lines }: { lines: readonly string[] }) {
  if (lines.length === 0) return null;
  return (
    <Banner tone="info" title="Not known for this session" actions={termHelp('unknown')}>
      <Stack gap={0.5}>
        {lines.map((line) => (
          <Text key={line} size="sm">
            {line}
          </Text>
        ))}
      </Stack>
    </Banner>
  );
}
