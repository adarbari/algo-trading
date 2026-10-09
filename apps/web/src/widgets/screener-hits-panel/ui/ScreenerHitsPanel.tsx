/**
 * Explore's "Screener hits" for one ticker: each of the user's screeners that picked it in the
 * latest session (its run for exactly that session, never an older one), with the decision,
 * rank and score its run stored and why it is not simply qualified.
 */
import { Button, ExpandableRow, Panel, Stack, Text } from '@algotrade/ui';
import { useState } from 'react';

import {
  CriteriaScorecard,
  DecisionBadge,
  decisionLabel,
  useScreenerHits,
} from '@/entities/screen';

export interface ScreenerHitsPanelProps {
  symbol: string;
  /** Opens the screener's results page; with it each open screener offers a button to it. */
  onOpenScreener?: (screenerId: string) => void;
  /** The screener the reader came from (Ideas' `via`): its row opens first. */
  via?: string | null;
}

export function ScreenerHitsPanel({ symbol, onOpenScreener, via = null }: ScreenerHitsPanelProps) {
  const query = useScreenerHits(symbol);
  const data = query.data;
  const hits = data?.hits ?? [];
  const [openId, setOpenId] = useState<string | null>(via);
  return (
    <Panel
      title="Screener hits"
      description={data?.session ? `Session ${data.session}` : undefined}
      state={
        query.isError && !data
          ? 'error'
          : query.isPending
            ? 'loading'
            : hits.length === 0
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
        <Stack gap={1}>
          {hits.map(({ screener, result }) => (
            <ExpandableRow
              key={screener.id}
              title={screener.name}
              badge={<DecisionBadge decision={result.decision} />}
              secondary={
                [
                  result.score === null ? null : `score ${String(Math.round(result.score))}`,
                  result.change ? decisionLabel(result.change).toLowerCase() : null,
                ]
                  .filter(Boolean)
                  .join(' · ') || undefined
              }
              essential={`#${String(result.rank)}`}
              open={openId === screener.id}
              onOpenChange={(open) => {
                setOpenId(open ? screener.id : null);
              }}
            >
              <Stack gap={2}>
                <CriteriaScorecard
                  screenerId={screener.id}
                  entries={result.criteria}
                  label={`${screener.name} criteria for ${symbol}`}
                />
                {onOpenScreener ? (
                  <Stack direction="row">
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => {
                        onOpenScreener(screener.id);
                      }}
                    >
                      {`Open ${screener.name}`}
                    </Button>
                  </Stack>
                ) : null}
              </Stack>
            </ExpandableRow>
          ))}
        </Stack>
      </Stack>
    </Panel>
  );
}
