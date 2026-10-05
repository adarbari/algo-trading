/**
 * Trader > Screeners > one screener (Results, `/screeners/$id`): the latest run as a review
 * table with the row under review beside it (its decision, criteria and price chart), and
 * "Edit criteria" for the Builder. Reviewing comes first, editing is one click away. The
 * review is keyboard-first: j / k move, c adds the ticker to the compare set, x hides it for
 * now, Enter opens it in Explore.
 */
import { Button, Heading, Stack, Text, type ChartRange } from '@algotrade/ui';
import { useState } from 'react';

import { PickDetail } from '@/widgets/pick-detail';
import { PriceChartPanel } from '@/widgets/price-chart-panel';
import { ScreenerResults } from '@/widgets/screener-results';

export interface ScreenerResultsPageProps {
  /** The screener shown. */
  id: string;
  /** Open the Builder for this screener. */
  onEdit: () => void;
  /** Open a ticker in Explore. */
  onOpenTicker: (symbol: string) => void;
  /** Open the tickers added to the compare set in Explore. */
  onCompare: (symbols: readonly string[]) => void;
}

export function ScreenerResultsPage({
  id,
  onEdit,
  onOpenTicker,
  onCompare,
}: ScreenerResultsPageProps) {
  const [focusId, setFocusId] = useState<string | null>(null);
  const [compared, setCompared] = useState<readonly string[]>([]);
  const [dismissed, setDismissed] = useState<ReadonlySet<string>>(new Set());
  const [range, setRange] = useState<ChartRange>('1Y');
  const toggle = (symbol: string) => {
    setCompared((now) =>
      now.includes(symbol) ? now.filter((s) => s !== symbol) : [...now, symbol],
    );
  };
  const hide = (instrumentId: string) => {
    setDismissed((now) => new Set(now).add(instrumentId));
  };
  return (
    <Stack gap={3}>
      <Stack direction="row" gap={3} align="center" justify="between" wrap>
        <Stack gap={1}>
          <Heading level={1}>{id}</Heading>
          <Text size="sm" tone="secondary">
            What this screener found in its latest run. Add any catalogue feature as a column; your
            columns and filters are saved as your view of it.
          </Text>
        </Stack>
        <Stack direction="row" gap={2} align="center">
          {compared.length >= 2 ? (
            <Button
              onClick={() => {
                onCompare(compared);
              }}
            >
              {`Compare ${String(compared.length)} in Explore`}
            </Button>
          ) : null}
          <Button variant="secondary" onClick={onEdit}>
            Edit criteria
          </Button>
        </Stack>
      </Stack>
      <ScreenerResults
        id={id}
        onOpen={onOpenTicker}
        focusId={focusId}
        onFocusChange={(row) => {
          setFocusId(row.instrument_id);
        }}
        onToggleCompare={(row) => {
          toggle(row.symbol ?? row.instrument_id);
        }}
        onDismiss={(row) => {
          hide(row.instrument_id);
        }}
        dismissed={dismissed}
        onShowDismissed={() => {
          setDismissed(new Set());
        }}
        renderDetail={({ row, table }) => (
          <Stack gap={3}>
            <PickDetail
              row={row}
              criteria={table.criteria}
              compared={compared.includes(row.symbol ?? row.instrument_id)}
              onOpen={onOpenTicker}
              onToggleCompare={() => {
                toggle(row.symbol ?? row.instrument_id);
              }}
              onDismiss={() => {
                hide(row.instrument_id);
              }}
            />
            {row.symbol ? (
              <PriceChartPanel symbol={row.symbol} range={range} onRangeChange={setRange} />
            ) : null}
          </Stack>
        )}
      />
    </Stack>
  );
}
