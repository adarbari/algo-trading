/** Why a calculator has no figures: the ticker is unknown, the request failed, or the server's public gap. */
import { Stack, Text } from '@algotrade/ui';
import type { ReactNode } from 'react';

import { termHelp } from '@/features/guide-help';
import { ApiError } from '@/shared/api';

/** The message of a failed preview: an unknown ticker (404) is said plainly. */
export function failureMessage(symbol: string, error: unknown): string {
  return error instanceof ApiError && error.status === 404
    ? `${symbol} is not in the reference snapshot for the session.`
    : `The ${symbol} calculator failed to load.`;
}

/** A gap in public words with its Guide help button. */
export function GapLine({ gap }: { gap: { kind_text: string; guide_term: string } }): ReactNode {
  return (
    <Stack direction="row" gap={1} align="center">
      <Text>{gap.kind_text}</Text>
      {termHelp(gap.guide_term)}
    </Stack>
  );
}
