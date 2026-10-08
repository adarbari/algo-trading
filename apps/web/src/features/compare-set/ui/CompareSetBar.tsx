/**
 * The compare set as a bar: each ticker as a TickerTag in its series colour (removable), and
 * which ticker the detail tabs show (the focused one).
 */
import { Button, Select, Stack, Text, TickerTag } from '@algotrade/ui';

import { MAX_COMPARE, seriesAt } from '../model/compare-set';

export interface CompareSetBarProps {
  symbols: readonly string[];
  /** The ticker the detail tabs show. */
  focused: string | null;
  onRemove: (symbol: string) => void;
  onClear: () => void;
  onFocus: (symbol: string) => void;
  /** Open the detail for this ticker (the focused one, else the first): the phone's sheet. */
  onOpen: (symbol: string) => void;
}

export function CompareSetBar({
  symbols,
  focused,
  onRemove,
  onClear,
  onFocus,
  onOpen,
}: CompareSetBarProps) {
  const choices = [...new Set([...(focused ? [focused] : []), ...symbols])];
  return (
    <Stack direction="row" gap={2} wrap align="center" justify="between">
      <Stack direction="row" gap={1} wrap align="center">
        {symbols.length === 0 ? (
          <Text size="sm" tone="muted">
            Tick up to {MAX_COMPARE} tickers in the table to compare them.
          </Text>
        ) : (
          <>
            <Text size="sm" tone="muted">
              Comparing
            </Text>
            {symbols.map((symbol, i) => {
              const series = seriesAt(i);
              return (
                <TickerTag
                  key={symbol}
                  symbol={symbol}
                  {...(series ? { series } : {})}
                  onRemove={() => {
                    onRemove(symbol);
                  }}
                  removeContext="from compare"
                />
              );
            })}
            <Button variant="ghost" size="sm" onClick={onClear}>
              Clear
            </Button>
          </>
        )}
      </Stack>
      {choices.length > 0 ? (
        <Stack direction="row" gap={1} align="center">
          <Text size="sm" tone="muted">
            Detail for
          </Text>
          <Select
            aria-label="Ticker shown in the detail tabs"
            size="sm"
            width="auto"
            options={choices.map((s) => ({ value: s, label: s }))}
            value={focused ?? choices[0] ?? ''}
            onValueChange={onFocus}
          />
          <Button
            size="sm"
            variant="primary"
            onClick={() => {
              onOpen(focused ?? symbols[0] ?? '');
            }}
          >
            {symbols.length > 1 ? `Compare ${symbols.length}` : 'Open detail'}
          </Button>
        </Stack>
      ) : null}
    </Stack>
  );
}
