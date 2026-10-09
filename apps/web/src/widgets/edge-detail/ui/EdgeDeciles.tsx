/**
 * Top vs bottom decile as bars: the in-sample mean outcome of each tenth of the screen's ranking,
 * best-ranked first, as signed bars around a zero axis (`BarList` `diverging`). Every number is
 * served; a decile the run did not store is left out, and without any the panel says so.
 */
import { BarList, Panel, Stack, Text, type BarListItem } from '@algotrade/ui';

import { GuideHelp } from '@/features/guide-help';

export interface EdgeDecilesProps {
  /** The in-sample mean outcome per tenth, best-ranked first (empty: not stored). */
  deciles: readonly (number | null)[];
}

export function EdgeDeciles({ deciles }: EdgeDecilesProps) {
  const items: BarListItem[] = deciles.flatMap((value, i) =>
    value == null ? [] : [{ id: `decile-${i + 1}`, label: `Decile ${i + 1}`, value }],
  );
  return (
    <Panel
      title="Top vs bottom decile"
      state={items.length === 0 ? 'empty' : 'ready'}
      emptyMessage="Not stored for this result."
      actions={
        <Stack direction="row" gap={1} align="center">
          <Text size="xs" tone="muted">
            In-sample
          </Text>
          <GuideHelp entry={{ kind: 'term', id: 'top_vs_bottom_decile' }} />
        </Stack>
      }
    >
      <BarList
        label="Mean outcome by decile"
        items={items}
        diverging
        format={{ kind: 'delta', digits: 1 }}
      />
    </Panel>
  );
}
