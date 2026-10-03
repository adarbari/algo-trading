/**
 * The ticker table's filter bar: the search box and the filter chips (optionable, security
 * type, leveraged, high liquidity), the active many-valued filters as removable chips, and
 * "+ Filter" for the rest. Controlled: the caller keeps the filters (in the URL).
 */
import { Chip, SearchInput, Stack } from '@algotrade/ui';

import { liquidityLabel, TYPE_CHIPS, typeLabel, type TickerFilters } from '../model/filters';

import { MoreFilters } from './MoreFilters';

export interface TickerFilterBarProps {
  filters: TickerFilters;
  onChange: (filters: TickerFilters) => void;
  /** Rows are being fetched for the current filters. */
  loading?: boolean;
}

export function TickerFilterBar({ filters, onChange, loading = false }: TickerFilterBarProps) {
  const set = (patch: Partial<TickerFilters>) => {
    onChange({ ...filters, ...patch });
  };
  const typeIsChip = TYPE_CHIPS.some((t) => t.value === filters.type);
  return (
    <Stack gap={2}>
      <SearchInput
        aria-label="Filter tickers"
        placeholder="Ticker, name or sector…"
        value={filters.q ?? ''}
        onValueChange={(q) => {
          set({ q: q || undefined });
        }}
        loading={loading}
      />
      <Stack direction="row" gap={1} wrap align="center">
        <Chip
          label="Optionable"
          selected={filters.optionable === true}
          onSelectedChange={(on) => {
            set({ optionable: on ? true : undefined });
          }}
        />
        {TYPE_CHIPS.map((type) => (
          <Chip
            key={type.value}
            label={type.label}
            selected={filters.type === type.value}
            onSelectedChange={(on) => {
              set({ type: on ? type.value : undefined });
            }}
          />
        ))}
        <Chip
          label="Leveraged"
          selected={filters.leveraged === true}
          onSelectedChange={(on) => {
            set({ leveraged: on ? true : undefined });
          }}
        />
        <Chip
          label="Liquidity: High"
          selected={filters.liquidity === 'HIGH'}
          onSelectedChange={(on) => {
            set({ liquidity: on ? 'HIGH' : undefined });
          }}
        />
        {filters.type && !typeIsChip ? (
          <Chip
            label={`Type: ${typeLabel(filters.type)}`}
            onRemove={() => {
              set({ type: undefined });
            }}
          />
        ) : null}
        {filters.sector ? (
          <Chip
            label={`Sector: ${filters.sector}`}
            onRemove={() => {
              set({ sector: undefined });
            }}
          />
        ) : null}
        {filters.liquidity && filters.liquidity !== 'HIGH' ? (
          <Chip
            label={`Liquidity: ${liquidityLabel(filters.liquidity)}`}
            onRemove={() => {
              set({ liquidity: undefined });
            }}
          />
        ) : null}
        <MoreFilters filters={filters} onChange={onChange} />
      </Stack>
    </Stack>
  );
}
