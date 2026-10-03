/**
 * The option chain's columns. Simple: strike, bid, ask, open interest and the contract in
 * plain English. Pro adds last, volume, implied vol, delta and the other Greeks. Strikes in
 * the 8-15 delta band carry a badge (the band short-premium sellers look at).
 */
import { Stack, StatusBadge, Text, type DataTableColumn } from '@algotrade/ui';

import { DELTA_BAND, type ChainRow } from '@/entities/chain';

export type ChainView = 'simple' | 'pro';

const pct = (x: number) => Math.round(x * 100);
export const BAND_LABEL = `${pct(DELTA_BAND[0])}–${pct(DELTA_BAND[1])} Δ`;

const strike: DataTableColumn<ChainRow> = {
  id: 'strike',
  header: 'Strike',
  value: (r) => r.strike,
  format: { kind: 'currency' },
  align: 'start',
  width: 'md',
  cell: ({ row, formatted }) => (
    <Stack direction="row" gap={2} align="center">
      <Text weight="semibold" numeric>
        {formatted.text}
      </Text>
      {row.inBand ? (
        <StatusBadge tone="accent" title={`|delta| between ${DELTA_BAND[0]} and ${DELTA_BAND[1]}`}>
          {BAND_LABEL}
        </StatusBadge>
      ) : null}
    </Stack>
  ),
};

const money = (id: 'bid' | 'ask' | 'last', header: string): DataTableColumn<ChainRow> => ({
  id,
  header,
  value: (r) => r[id],
  format: { kind: 'currency' },
});

const SIMPLE: readonly DataTableColumn<ChainRow>[] = [
  strike,
  money('bid', 'Bid'),
  money('ask', 'Ask'),
  { id: 'oi', header: 'Open interest', value: (r) => r.openInterest, format: { kind: 'number' } },
];

const PRO: readonly DataTableColumn<ChainRow>[] = [
  money('last', 'Last'),
  { id: 'volume', header: 'Volume', value: (r) => r.volume, format: { kind: 'number' } },
  {
    id: 'iv',
    header: 'IV',
    description: 'Implied volatility (the feed’s, annualised)',
    value: (r) => r.iv,
    format: { kind: 'percent' },
  },
  { id: 'delta', header: 'Delta', value: (r) => r.delta, format: { kind: 'number', digits: 3 } },
  { id: 'gamma', header: 'Gamma', value: (r) => r.gamma, format: { kind: 'number', digits: 4 } },
  {
    id: 'theta',
    header: 'Theta',
    description: 'Price change per calendar day',
    value: (r) => r.theta,
    format: { kind: 'number', digits: 3 },
  },
  {
    id: 'vega',
    header: 'Vega',
    description: 'Price change per volatility point',
    value: (r) => r.vega,
    format: { kind: 'number', digits: 3 },
  },
];

const plain: DataTableColumn<ChainRow> = {
  id: 'plain',
  header: 'In plain English',
  value: (r) => r.plain,
  sortable: false,
  grow: true,
  width: 'xl',
  cell: ({ row }) => (
    <Text size="sm" tone="secondary" truncate title={row.plain}>
      {row.plain}
    </Text>
  ),
};

export function chainColumns(view: ChainView): DataTableColumn<ChainRow>[] {
  return view === 'pro' ? [...SIMPLE, ...PRO, plain] : [...SIMPLE, plain];
}
