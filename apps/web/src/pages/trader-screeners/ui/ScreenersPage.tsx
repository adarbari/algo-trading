/** Trader > Screeners: your screeners and the site presets, with "+ New screener". */
import { Button, Heading, Stack, Text } from '@algotrade/ui';

import { ScreenerList } from '@/widgets/screener-list';

export interface ScreenersPageProps {
  /** Open a screener in the Builder. */
  onOpen: (id: string) => void;
  /** Start a new screener. */
  onNew: () => void;
}

export function ScreenersPage({ onOpen, onNew }: ScreenersPageProps) {
  return (
    <Stack gap={3}>
      <Stack direction="row" gap={3} align="center" justify="between" wrap>
        <Stack gap={1}>
          <Heading level={1}>Screeners</Heading>
          <Text size="sm" tone="secondary">
            Build a screener from the feature catalogue, preview it live, finalize a version and
            schedule it nightly.
          </Text>
        </Stack>
        <Button variant="primary" onClick={onNew}>
          + New screener
        </Button>
      </Stack>
      <ScreenerList onOpen={onOpen} />
    </Stack>
  );
}
