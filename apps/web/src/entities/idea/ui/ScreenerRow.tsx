/**
 * One screener in the priority list: its rank, name, where it comes from, its best finds and
 * how many tickers its run picked (both counted by the server over the whole run), or that it
 * did not run for the session (and why).
 */
import { Button, Mono, Stack, Text } from '@algotrade/ui';

import { unknownText } from '@/entities/availability';

import type { ScreenerSummary } from '../model/idea';

const score = (value: number | null) => (value === null ? '—' : value.toFixed(0));

export interface ScreenerRowProps {
  screener: ScreenerSummary;
  rank: number;
  /** Open the screener's results; with it the name is a button. */
  onOpen?: (screenerId: string) => void;
}

export function ScreenerRow({ screener, rank, onOpen }: ScreenerRowProps) {
  const meta = [screener.owner, screener.version === null ? null : `v${screener.version}`]
    .filter(Boolean)
    .join(' · ');
  const finds =
    screener.notRun !== null
      ? 'Not run for this session'
      : screener.top.length > 0
        ? screener.top.map((t) => `${t.symbol} ${score(t.score)}`).join(' · ')
        : 'No picks';
  return (
    <Stack direction="row" gap={3} align="center" justify="between">
      <Stack direction="row" gap={3} align="center">
        <Mono tone="muted">{rank}</Mono>
        <Stack gap={0}>
          {onOpen ? (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                onOpen(screener.id);
              }}
            >
              {screener.name}
            </Button>
          ) : (
            <Text weight="medium">{screener.name}</Text>
          )}
          {meta ? (
            <Text size="xs" tone="muted">
              {meta}
            </Text>
          ) : null}
          <Text
            size="xs"
            tone={screener.notRun !== null ? 'muted' : 'secondary'}
            {...(screener.notRun === null ? {} : { title: unknownText(screener.notRun) })}
          >
            {finds}
          </Text>
        </Stack>
      </Stack>
      <Stack gap={0} align="end">
        <Mono weight="medium" tone={screener.notRun !== null ? 'muted' : 'default'}>
          {screener.notRun !== null ? '—' : screener.picked}
        </Mono>
        <Text size="xs" tone="muted">
          {screener.notRun !== null ? 'not run' : 'picked'}
        </Text>
      </Stack>
    </Stack>
  );
}
