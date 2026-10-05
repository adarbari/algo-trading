/**
 * Options: the focused ticker's chain for one expiry. Opens on the expiry the liquidity
 * rollup targets (the standard monthly near 35 days), else the first at least three weeks
 * out. Puts or calls; Simple (strike, bid, ask, open interest, plain English) or Pro (adds
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
  chainRows,
  defaultExpiry,
  expiryLabel,
  spotOf,
  useOptionChain,
  type ChainRow,
  type OptionRight,
} from '@/entities/chain';
import { useInstrument } from '@/entities/instrument';
import { ApiError, feature } from '@/shared/api';

import { BAND_LABEL, chainColumns, type ChainView } from '../model/columns';

import { ExpiryTabs } from './ExpiryTabs';

const TARGET_EXPIRY = feature('rollup.option_liquidity@v1.target_expiry');

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
  const detail = useInstrument(symbol);
  const target = detail.data?.features[TARGET_EXPIRY];
  const wanted = expiry ?? (typeof target === 'string' ? target : null);
  // Wait for the detail so the first request asks for one expiry, not the whole chain.
  const chain = useOptionChain(detail.isPending ? null : symbol, wanted);
  const data = chain.data;
  const active = wanted ?? (data ? defaultExpiry(data) : null);
  const rows = useMemo(
    () =>
      data && active
        ? chainRows(data, { right, expiry: active, symbol, nearMoney: !allStrikes })
        : [],
    [data, active, right, symbol, allStrikes],
  );
  const columns = useMemo(() => chainColumns(view), [view]);

  const missing = chain.error instanceof ApiError && chain.error.status === 404;
  if (missing) {
    return (
      <EmptyState
        bordered
        title={`No option chain for ${symbol}`}
        description="The nightly chain run stored no options for this ticker."
      />
    );
  }
  const side = right === 'P' ? 'puts' : 'calls';
  const title =
    data && active
      ? `${symbol} options · ${expiryLabel(data.session, active)} · ${side}`
      : `${symbol} options`;
  const ours = data?.our_iv?.['iv30'];
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
      state={chain.isError ? 'error' : 'ready'}
      errorMessage={`${symbol} options failed to load.`}
      onRetry={() => void chain.refetch()}
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
                value: spotOf(data),
                format: { kind: 'currency' },
              },
              {
                id: 'iv',
                label: 'IV30 (ours)',
                value: typeof ours === 'number' ? ours : null,
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
          <ExpiryTabs
            session={data.session}
            expiries={data.expiries}
            value={active}
            onChange={props.onExpiryChange}
          >
            <DataTable<ChainRow>
              label={`${symbol} ${side}, ${active}`}
              columns={columns}
              rows={rows}
              getRowId={(r) => r.id}
              defaultSort={{ columnId: 'strike', direction: 'asc' }}
              visibleRows={14}
              status={chain.isFetching && rows.length === 0 ? 'loading' : 'ready'}
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
