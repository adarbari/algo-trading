/**
 * "Where a ticker stands", the head of the ticker page: three cards from stored facts for the
 * session. The setups that picked it tonight (each linked, with its verdict and its place; none is
 * a normal answer), the avoid-list checks, and the next report with the move the options market
 * prices for it. Every value is the server's; a fact the session lacks says so with the reason.
 * Not a verdict: each card has its Guide button.
 */
import {
  EmptyState,
  Grid,
  Heading,
  KeyValue,
  Panel,
  Stack,
  StatusBadge,
  Text,
  TextLink,
} from '@algotrade/ui';
import { useMemo } from 'react';

import { verdictLabel, verdictTone } from '@/entities/edge';
import { useInstrumentFacts, usePickedBy } from '@/entities/instrument';
import { termHelp } from '@/features/guide-help';

import { CHECKS, NEXT, rows, STANDS_FEATURES } from '../model/stands';

export interface TickerStandsProps {
  symbol: string;
}

export function TickerStands({ symbol }: TickerStandsProps) {
  const picked = usePickedBy(symbol);
  const facts = useInstrumentFacts(symbol, STANDS_FEATURES);
  const values = useMemo(
    () => new Map((facts.data?.instrument?.features ?? []).map((v) => [v.name, v])),
    [facts.data],
  );
  const factState = facts.isError ? 'error' : facts.isPending ? 'loading' : 'ready';
  const pickedState = picked.isError ? 'error' : picked.isPending ? 'loading' : 'ready';
  return (
    <Stack gap={2}>
      <Stack direction="row" gap={1} align="center">
        <Heading level={2}>Where {symbol} stands</Heading>
        {termHelp('ticker_where_it_stands')}
      </Stack>
      <Grid columns={3} gap={3} collapse="lg" align="start">
        <Panel
          title="Setups that picked it"
          headingLevel={3}
          actions={termHelp('ticker_picked_by')}
          state={pickedState}
          loadingLabel="Loading the setups…"
          errorMessage="The setups failed to load."
          onRetry={() => void picked.refetch()}
        >
          {(picked.data ?? []).length === 0 ? (
            <EmptyState
              compact
              title="None tonight"
              action={<TextLink href="/edges">See every setup's rules</TextLink>}
            />
          ) : (
            <Stack gap={3}>
              {(picked.data ?? []).map((s) => (
                <Stack key={s.edgeId} gap={1} align="start">
                  <StatusBadge tone={verdictTone(s.level)}>{verdictLabel(s.level)}</StatusBadge>
                  <TextLink href={`/edges?edge=${s.edgeId}`}>{s.edgeName}</TextLink>
                  <Text size="sm" tone="muted">{`Place ${String(s.place)} in ${s.tab}`}</Text>
                </Stack>
              ))}
            </Stack>
          )}
        </Panel>
        <Panel
          title="Avoid-list checks"
          headingLevel={3}
          actions={termHelp('ticker_avoid_checks')}
          state={factState}
          loadingLabel="Loading the checks…"
          errorMessage="The checks failed to load."
          onRetry={() => void facts.refetch()}
        >
          <KeyValue label="Avoid-list checks" items={rows(values, CHECKS)} />
        </Panel>
        <Panel
          title="Report ahead"
          headingLevel={3}
          actions={termHelp('ticker_next_report')}
          state={factState}
          loadingLabel="Loading the report…"
          errorMessage="The report failed to load."
          onRetry={() => void facts.refetch()}
        >
          <KeyValue label="Next report" items={rows(values, NEXT)} />
        </Panel>
      </Grid>
    </Stack>
  );
}
