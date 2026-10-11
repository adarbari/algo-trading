/** A figure's label with its Guide help button beside it (a strip cell, a key-value row). */
import { Stack, Text } from '@algotrade/ui';
import type { ReactNode } from 'react';

import { termHelp } from './GuideHelp';

export function Labelled({ text, help }: { text: string; help: string }): ReactNode {
  return (
    <Stack direction="row" gap={1} align="center">
      <Text size="xs" tone="muted">
        {text}
      </Text>
      {termHelp(help)}
    </Stack>
  );
}
