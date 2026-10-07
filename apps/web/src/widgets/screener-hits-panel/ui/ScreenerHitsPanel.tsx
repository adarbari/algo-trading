/**
 * Explore's "Screener hits" for one ticker: each of the user's screeners that picked it in the
 * latest session (its run for exactly that session, never an older one), with the decision,
 * rank and score its run stored and why it is not simply qualified.
 */
import { Button, KeyValue, Panel, Stack, Text, type KeyValueItem } from '@algotrade/ui';

import { DecisionBadge, decisionLabel, useScreenerHits } from '@/entities/screen';

export interface ScreenerHitsPanelProps {
  symbol: string;
  /** Opens the screener's results page; with it each screener's name is a button. */
  onOpenScreener?: (screenerId: string) => void;
}

export function ScreenerHitsPanel({ symbol, onOpenScreener }: ScreenerHitsPanelProps) {
  const query = useScreenerHits(symbol);
  const data = query.data;
  const items = (data?.hits ?? []).map(({ screener, result }): KeyValueItem => ({
    id: screener.id,
    label: onOpenScreener ? (
      <Button
        variant="ghost"
        size="sm"
        onClick={() => {
          onOpenScreener(screener.id);
        }}
      >
        {screener.name}
      </Button>
    ) : (
      screener.name
    ),
    hint: [
      `#${String(result.rank)}`,
      result.score === null ? null : `score ${String(Math.round(result.score))}`,
      result.change ? decisionLabel(result.change).toLowerCase() : null,
      result.reasons || null,
    ]
      .filter(Boolean)
      .join(' · '),
    value: <DecisionBadge decision={result.decision} />,
  }));
  return (
    <Panel
      title="Screener hits"
      description={data?.session ? `Session ${data.session}` : undefined}
      state={
        query.isError && !data
          ? 'error'
          : query.isPending
            ? 'loading'
            : items.length === 0
              ? 'empty'
              : 'ready'
      }
      emptyMessage={
        data === null
          ? `${symbol} is not in the reference snapshot.`
          : `None of your screeners picked ${symbol} in the session${data?.session ? ` ${data.session}` : ''}.`
      }
      errorMessage="The screener hits failed to load."
      onRetry={() => void query.refetch()}
    >
      <Stack gap={2}>
        <Text size="sm" tone="secondary">
          The screeners whose run for this session picked it.
        </Text>
        <KeyValue label={`Screeners that picked ${symbol}`} items={items} alignValues="end" />
      </Stack>
    </Panel>
  );
}
