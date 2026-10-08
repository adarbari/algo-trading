/**
 * The ticker table's filter bar: the search box and the filter chips (optionable, security
 * type, leveraged, high liquidity), the active many-valued filters as removable chips, and
 * the fields of the rest in the filter bar's "more" panel. Controlled: the caller keeps the filters (in the URL).
 */
import { Chip, FilterBar, SearchInput } from '@algotrade/ui';

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
  const activeChips = [
    filters.type && !typeIsChip ? (
      <Chip
        key="type"
        label={`Type: ${typeLabel(filters.type)}`}
        onRemove={() => {
          set({ type: undefined });
        }}
      />
    ) : null,
    filters.sector ? (
      <Chip
        key="sector"
        label={`Sector: ${filters.sector}`}
        onRemove={() => {
          set({ sector: undefined });
        }}
      />
    ) : null,
    filters.liquidity && filters.liquidity !== 'HIGH' ? (
      <Chip
        key="liquidity"
        label={`Liquidity: ${liquidityLabel(filters.liquidity)}`}
        onRemove={() => {
          set({ liquidity: undefined });
        }}
      />
    ) : null,
  ].filter(Boolean);
  const { q: _q, ...rest } = filters;
  const activeCount = Object.values(rest).filter((v) => v !== undefined).length;
  return (
    <FilterBar
      activeCount={activeCount}
      search={
        <SearchInput
          aria-label="Filter tickers"
          placeholder="Ticker or name…"
          value={filters.q ?? ''}
          onValueChange={(q) => {
            set({ q: q || undefined });
          }}
          loading={loading}
        />
      }
      quick={
        <>
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
        </>
      }
      active={activeChips.length > 0 ? <>{activeChips}</> : null}
      more={<MoreFilters filters={filters} onChange={onChange} />}
    />
  );
}
