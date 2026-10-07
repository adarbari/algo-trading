/**
 * Events, what is coming and what it filed: the dated events of the next 90 days (own and a
 * fund's reference earnings, macro releases, expiry and index days) with the 7-90 day expiry
 * ladder (the longest expiry still clear of earnings and macro marked), a leveraged fund's
 * reference ("tracks NVDA", opens it), the 8-Ks of the last 24 months on a timeline and in a
 * list, and every part not known for the session with its reason. All wording is the API's.
 */
import {
  Banner,
  Button,
  DataTable,
  EventTimeline,
  ExpiryLadder,
  Panel,
  Stack,
  Text,
} from '@algotrade/ui';
import { useMemo } from 'react';

import {
  aheadItems,
  filingItem,
  gapLines,
  ladderRows,
  useInstrumentEventStudy,
} from '@/entities/event';

import { AHEAD_COLUMNS, FILING_COLUMNS, type FilingRow } from '../model/columns';

export interface EventStudyPanelProps {
  symbol: string;
  /** Called with the ticker of the fund's reference (opens it in Explore). */
  onSelectSymbol?: (symbol: string) => void;
}

export function EventStudyPanel({ symbol, onSelectSymbol }: EventStudyPanelProps) {
  const query = useInstrumentEventStudy(symbol);
  const study = query.data;
  const ahead = useMemo(() => (study ? aheadItems(study) : []), [study]);
  const rows = useMemo(() => (study ? ladderRows(study) : []), [study]);
  const filings = useMemo<FilingRow[]>(
    () =>
      (study?.filings ?? []).map((filing, i) => ({
        id: `${filing.accepted}-${String(i)}`,
        filing,
        item: filingItem(filing),
      })),
    [study],
  );
  const gaps = useMemo(() => gapLines(study?.gaps ?? []), [study]);
  const reference = study?.reference ?? null;
  const oldest = filings.at(-1)?.item.date;
  const state = query.isError ? 'error' : study === null ? 'empty' : 'ready';
  const missing = `${symbol} is not in the reference snapshot for the session.`;
  return (
    <Stack gap={4}>
      <Panel
        title={`${symbol} · what is coming`}
        description={`Dated events of the next ${String(study?.days ?? 90)} days and the listed expiries`}
        state={state}
        errorMessage={`${symbol} events failed to load.`}
        emptyMessage={missing}
        onRetry={() => void query.refetch()}
      >
        <Stack gap={3}>
          {reference?.symbol != null && (
            <Stack direction="row" gap={2} align="center">
              <Text size="sm">{`Tracks ${reference.symbol}`}</Text>
              {onSelectSymbol && (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    onSelectSymbol(reference.symbol ?? '');
                  }}
                >
                  {`Open ${reference.symbol}`}
                </Button>
              )}
            </Stack>
          )}
          {gaps.length > 0 && (
            <Banner tone="info" title="Not known for this session">
              <Stack gap={0.5}>
                {gaps.map((line) => (
                  <Text key={line} size="sm">
                    {line}
                  </Text>
                ))}
              </Stack>
            </Banner>
          )}
          <DataTable<(typeof ahead)[number]>
            label={`Events ahead for ${symbol}`}
            columns={AHEAD_COLUMNS}
            rows={ahead}
            getRowId={(e) => `${e.kind}-${e.date}-${e.label}`}
            visibleRows={10}
            status={query.isPending ? 'loading' : 'ready'}
            emptyMessage={`No dated events ahead for ${symbol}.`}
          />
          <ExpiryLadder
            label={`${symbol} expiries and the events they span`}
            rows={rows}
            status={query.isPending ? 'loading' : 'ready'}
            emptyMessage="No listed expiry 7 to 90 days out is stored for the session."
          />
        </Stack>
      </Panel>
      <Panel
        title={`${symbol} · filings`}
        description={`8-Ks of the last ${String(study?.months ?? 24)} months`}
        flush
        state={state}
        errorMessage={`${symbol} filings failed to load.`}
        emptyMessage={missing}
        onRetry={() => void query.refetch()}
      >
        <Stack gap={3}>
          <EventTimeline
            label={`${symbol} filings`}
            events={filings.map((f) => f.item)}
            start={oldest ?? study?.session ?? ''}
            end={study?.session ?? ''}
            status={query.isPending ? 'loading' : 'ready'}
            emptyMessage={`No filings stored for ${symbol}.`}
          />
          <DataTable<FilingRow>
            label={`${symbol} filings list`}
            columns={FILING_COLUMNS}
            rows={filings}
            getRowId={(r) => r.id}
            defaultSort={{ columnId: 'date', direction: 'desc' }}
            visibleRows={10}
            status={query.isPending ? 'loading' : 'ready'}
            emptyMessage={`No filings stored for ${symbol}.`}
          />
        </Stack>
      </Panel>
    </Stack>
  );
}
