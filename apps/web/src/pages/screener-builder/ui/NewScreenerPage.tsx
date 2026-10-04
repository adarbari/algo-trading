/** Trader > Screeners > New: name a screener and pick its universe; its blank draft opens in the Builder. */
import { Heading, Panel, Stack, Text } from '@algotrade/ui';

import { NewScreenerForm } from '@/features/screener-builder';

export interface NewScreenerPageProps {
  /** The draft was created: open it in the Builder. */
  onCreated: (id: string) => void;
  /** Back to the list. */
  onCancel: () => void;
}

export function NewScreenerPage({ onCreated, onCancel }: NewScreenerPageProps) {
  return (
    <Stack gap={3}>
      <Stack gap={1}>
        <Text size="sm" tone="muted">
          Screeners / New
        </Text>
        <Heading level={1}>New screener</Heading>
      </Stack>
      <Panel title="Name and universe">
        <NewScreenerForm onCreated={onCreated} onCancel={onCancel} />
      </Panel>
    </Stack>
  );
}
