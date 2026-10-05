/**
 * Options: the focused ticker's chain for the session, one expiry at a time (GraphQL
 * `OptionChain`, then `OptionQuotes`). Opens on the expiry the liquidity rollup targets (the
 * standard monthly near 35 days), else the first at least three weeks out. Puts or calls; Simple (strike, bid, ask, open interest, plain English) or Pro (adds
 * implied vol and the Greeks); strikes near the money unless "All strikes"; the 8-15 delta
 * band is badged.
 */
import {
  Banner,
  Chip,
  DataTable,
  EmptyState,
  Panel,
  SegmentedControl,
  Stack,
  StatStrip,
} from '@algotrade/ui';
import { useMemo } from 'react';

import {
  chainFacts,
  chainRows,
  defaultExpiry,
  expiryLabel,
  useOptionChain,
  useOptionQuotes,
  type ChainRow,
  type OptionRight,
} from '@/entities/chain';

import { BAND_LABEL, chainColumns, type ChainView } from '../model/columns';

import { ExpiryTabs } from './ExpiryTabs';

export interface OptionsPanelProps {
  symbol: string;
  /** The chosen expiry (null: the default). */
  expiry: string | null;
  onExpiryChange: (expiry: string) => void;
  view: ChainView;
  onViewChange: (view: ChainView) => void;
  right: OptionRight;
  onRightChange: (right: OptionRight) => void;
  allStrikes: boolean;
  onAllStrikesChange: (all: boolean) => void;
}

export function OptionsPanel(props: OptionsPanelProps) {
  const { symbol, expiry, view, right, allStrikes } = props;
  const chain = useOptionChain(symbol);
  const { target, spot, iv30 } = useMemo(() => chainFacts(chain.data?.features), [chain.data]);
  const data = chain.data?.chain ?? undefined;
  const listed = data?.expiries.some((e) => e.date === target) ? target : null;
  const active = expiry ?? listed ?? (data ? defaultExpiry(data) : null);
  const quotes = useOptionQuotes(data ? symbol : null, active, data?.session ?? null);
  const rows = useMemo(
    () =>
      active
        ? chainRows(quotes.data ?? [], {
            right,
            expiry: active,
            symbol,
            spot,
            nearMoney: !allStrikes,
          })
        : [],
    [quotes.data, active, right, symbol, spot, allStrikes],
  );
  const columns = useMemo(() => chainColumns(view), [view]);

  const missing = chain.data !== undefined && !data;
  if (missing) {
    return (
      <EmptyState
        bordered
        title={`No option chain for ${symbol}`}
        description="The nightly chain run stored no options for this ticker for the session."
      />
    );
  }
  const side = right === 'P' ? 'puts' : 'calls';
  const shown = data?.expiries.find((e) => e.date === active);
  const title = shown ? `${symbol} options · ${expiryLabel(shown)} · ${side}` : `${symbol} options`;
  return (
    <Panel
      title={title}
      actions={
        <Stack direction="row" gap={2} wrap align="center">
          <SegmentedControl<OptionRight>
            aria-label="Puts or calls"
            size="sm"
            options={[
              { value: 'P', label: 'Puts' },
              { value: 'C', label: 'Calls' },
            ]}
            value={right}
            onValueChange={props.onRightChange}
          />
          <SegmentedControl<ChainView>
            aria-label="Chain view"
            size="sm"
            options={[
              { value: 'simple', label: 'Simple', description: 'Strike, bid, ask, open interest' },
              { value: 'pro', label: 'Pro', description: 'Adds implied vol and the Greeks' },
            ]}
            value={view}
            onValueChange={props.onViewChange}
          />
          <Chip
            label="All strikes"
            selected={allStrikes}
            onSelectedChange={props.onAllStrikesChange}
          />
        </Stack>
      }
      state={chain.isError || quotes.isError ? 'error' : 'ready'}
      errorMessage={`${symbol} options failed to load.`}
      onRetry={() => {
        void chain.refetch();
        void quotes.refetch();
      }}
      footer={`${BAND_LABEL}: contracts whose |delta| is 0.08 to 0.15. Cboe delayed quotes for the session; IV and Greeks as the feed computes them.`}
    >
      <Stack gap={3}>
        {data?.status && data.status !== 'OK' ? (
          <Banner tone="warning" title="Chain incomplete">
            The chain run reported {data.status} for {symbol} on {data.session}.
          </Banner>
        ) : null}
        {data ? (
          <StatStrip
            label={`${symbol} underlying`}
            items={[
              {
                id: 'spot',
                label: 'Underlying',
                value: spot,
                format: { kind: 'currency' },
              },
              {
                id: 'iv',
                label: 'IV30 (ours)',
                value: iv30,
                format: { kind: 'percent' },
              },
              {
                id: 'session',
                label: 'Quotes from',
                value: data.session,
                format: { kind: 'date' },
                sub: data.status ?? undefined,
              },
            ]}
          />
        ) : null}
        {data && active ? (
          <ExpiryTabs chain={data} value={active} onChange={props.onExpiryChange}>
            <DataTable<ChainRow>
              label={`${symbol} ${side}, ${active}`}
              columns={columns}
              rows={rows}
              getRowId={(r) => r.id}
              defaultSort={{ columnId: 'strike', direction: 'asc' }}
              visibleRows={14}
              status={quotes.isFetching && rows.length === 0 ? 'loading' : 'ready'}
              emptyMessage={`No ${side} near the money for this expiry: try All strikes.`}
            />
          </ExpiryTabs>
        ) : (
          <DataTable<ChainRow>
            label={`${symbol} options`}
            columns={columns}
            rows={[]}
            getRowId={(r) => r.id}
            status="loading"
          />
        )}
      </Stack>
    </Panel>
  );
}
