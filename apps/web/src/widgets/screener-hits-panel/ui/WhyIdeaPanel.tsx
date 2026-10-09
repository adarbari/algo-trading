/**
 * Explore's "Why it is an idea" for one ticker the Ideas page opened: the screener that
 * surfaced it, with the decision, rank, score, change and reasons its run for the latest session
 * stored (the same read as the Screener hits tab, so nothing more is fetched). The per-criterion
 * values are not part of that read: the screener's results hold them, one link away.
 */
import { Button, KeyValue, Panel, Stack, Text, type KeyValueItem } from '@algotrade/ui';

import { DecisionBadge, decisionLabel, useScreenerHits } from '@/entities/screen';

export interface WhyIdeaPanelProps {
  symbol: string;
  /** The screener (config id) that surfaced the ticker. */
  screenerId: string;
  /** Opens that screener's results. */
  onOpenScreener: (screenerId: string) => void;
}

export function WhyIdeaPanel({ symbol, screenerId, onOpenScreener }: WhyIdeaPanelProps) {
  const query = useScreenerHits(symbol);
  const data = query.data;
  const hit = data?.hits.find((h) => h.screener.id === screenerId);
  const items: KeyValueItem[] = hit
    ? [
        {
          id: 'decision',
          label: 'Decision',
          value: <DecisionBadge decision={hit.result.decision} />,
        },
        { id: 'rank', label: 'Rank', value: `#${String(hit.result.rank)}` },
        ...(hit.result.score === null
          ? []
          : [{ id: 'score', label: 'Score', value: String(Math.round(hit.result.score)) }]),
        ...(hit.result.change
          ? [{ id: 'change', label: 'Since the last run', value: decisionLabel(hit.result.change) }]
          : []),
        ...(hit.result.reasons
          ? [{ id: 'reasons', label: 'Reasons', value: hit.result.reasons }]
          : []),
        ...(hit.result.flags.length > 0
          ? [{ id: 'flags', label: 'Flags', value: hit.result.flags.join(', ') }]
          : []),
      ]
    : [];
  const name = hit?.screener.name ?? screenerId;
  return (
    <Panel
      title="Why it is an idea"
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
      emptyMessage={`${name} did not pick ${symbol} in the latest session.`}
      errorMessage="The screener hit failed to load."
      onRetry={() => void query.refetch()}
      actions={
        <Button
          variant="secondary"
          size="sm"
          onClick={() => {
            onOpenScreener(screenerId);
          }}
        >
          {`Open ${name}`}
        </Button>
      }
    >
      <Stack gap={2}>
        <KeyValue label={`${name} on ${symbol}`} items={items} alignValues="end" />
        <Text size="sm" tone="muted">
          Criterion values are in the screener’s results.
        </Text>
      </Stack>
    </Panel>
  );
}
