/**
 * Holdings: what an ETF holds. The ten largest holdings with their weight in the fund, the
 * fund's total number of holdings, how much of the fund the ten make up and the issuer's date.
 * A holding in the universe opens its Explore row (`onSelectSymbol`); cash, futures, bonds and
 * foreign lines keep their name only. A fund with no stored holdings says so.
 */
import { DataTable, formatValue, Panel } from '@algotrade/ui';
import { useMemo } from 'react';

import {
  hasShort,
  shownWeight,
  sourceLabel,
  toRows,
  useEtfHoldings,
  type HoldingRow,
} from '@/entities/holdings';

import { holdingColumns } from '../model/columns';

const TOP = 10;
const number = (n: number) => formatValue(n, { kind: 'number' }).text;

export interface HoldingsPanelProps {
  /** The ETF's ticker. */
  symbol: string;
  /** Called with the ticker of a holding that is in the universe (opens its Explore row). */
  onSelectSymbol?: (symbol: string) => void;
}

export function HoldingsPanel({ symbol, onSelectSymbol }: HoldingsPanelProps) {
  const holdings = useEtfHoldings(symbol, TOP);
  const data = holdings.data;
  const rows = useMemo(() => (data ? toRows(data) : []), [data]);
  const columns = useMemo(() => holdingColumns(onSelectSymbol), [onSelectSymbol]);
  const empty = data !== undefined && rows.length === 0;
  const description =
    data && !empty
      ? summary(data.total, rows.length, shownWeight(data), hasShort(data), data.as_of)
      : undefined;
  const source = data ? sourceLabel(data.source) : null;
  return (
    <Panel
      title={`${symbol} · holdings`}
      description={description}
      flush
      state={holdings.isError ? 'error' : empty ? 'empty' : 'ready'}
      errorMessage={`${symbol} holdings failed to load.`}
      emptyMessage={
        data && !data.is_etf
          ? `${symbol} is not an ETF, so it has no holdings.`
          : `No holdings stored for ${symbol}: no issuer file or SEC filing covers it yet.`
      }
      onRetry={() => void holdings.refetch()}
      footer={source ? `Source: ${source}.` : undefined}
    >
      <DataTable<HoldingRow>
        label={`${symbol} top holdings`}
        columns={columns}
        rows={rows}
        getRowId={(row) => row.id}
        rowLines={2}
        defaultSort={{ columnId: 'rank', direction: 'asc' }}
        visibleRows={TOP}
        status={holdings.isPending ? 'loading' : 'ready'}
        emptyMessage={`No holdings stored for ${symbol}.`}
        {...(onSelectSymbol
          ? {
              onRowActivate: (row: HoldingRow) => {
                if (row.symbol !== null) onSelectSymbol(row.symbol);
              },
            }
          : {})}
      />
    </Panel>
  );
}

function summary(
  total: number,
  shown: number,
  weight: number,
  short: boolean,
  asOf: string | null,
): string {
  const share = formatValue(weight, { kind: 'percent', digits: 1 }).text;
  const size = short
    ? `${share} of the fund by size, short lines included`
    : `${share} of the fund`;
  const date = asOf ? ` · as of ${formatValue(asOf, { kind: 'date' }).text}` : '';
  return `Top ${number(shown)} of ${number(total)} holdings · ${size}${date}`;
}
