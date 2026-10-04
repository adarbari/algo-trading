/**
 * One screener in the priority list: its rank, name, where it comes from, its best finds and
 * how many tickers it qualified.
 */
import { Mono, Stack, Text } from '@algotrade/ui';

import type { ScreenerSummary } from '../model/idea';

const score = (value: number | null) => (value === null ? '—' : value.toFixed(0));

export function ScreenerRow({ screener, rank }: { screener: ScreenerSummary; rank: number }) {
  const meta = [screener.user, screener.version === null ? null : `v${screener.version}`]
    .filter(Boolean)
    .join(' · ');
  return (
    <Stack direction="row" gap={3} align="center" justify="between">
      <Stack direction="row" gap={3} align="center">
        <Mono tone="muted">{rank}</Mono>
        <Stack gap={0}>
          <Text weight="medium">{screener.id}</Text>
          {meta ? (
            <Text size="xs" tone="muted">
              {meta}
            </Text>
          ) : null}
          <Text size="xs" tone="secondary">
            {screener.top.length > 0
              ? screener.top.map((t) => `${t.symbol} ${score(t.score)}`).join(' · ')
              : 'No picks'}
          </Text>
        </Stack>
      </Stack>
      <Stack gap={0} align="end">
        <Mono weight="medium">{screener.qualified}</Mono>
        <Text size="xs" tone="muted">
          qualified
        </Text>
      </Stack>
    </Stack>
  );
}
