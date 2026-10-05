/**
 * "+ Filter": a popover with the filters that have many values (sector, liquidity class,
 * security type), their options read from the feature distributions across the universe.
 */
import { Button, Field, Popover, Select, Stack } from '@algotrade/ui';

import { distributionCategories, useFeatureDistribution } from '@/entities/feature';
import { feature } from '@/shared/api';

import { liquidityLabel, typeLabel, type TickerFilters } from '../model/filters';

const ANY = '';

export interface MoreFiltersProps {
  filters: TickerFilters;
  onChange: (filters: TickerFilters) => void;
}

export function MoreFilters({ filters, onChange }: MoreFiltersProps) {
  const sectors = useFeatureDistribution(feature('instrument.sector'));
  const liquidity = useFeatureDistribution(feature('feature.liquidity_class'));
  const types = useFeatureDistribution(feature('instrument.security_type'));
  const options = (values: string[], label: (v: string) => string, current?: string) => [
    { value: ANY, label: 'Any' },
    ...[...new Set([...values, ...(current ? [current] : [])])].map((v) => ({
      value: v,
      label: label(v),
    })),
  ];
  const set = (key: 'sector' | 'liquidity' | 'type') => (value: string) => {
    onChange({ ...filters, [key]: value === ANY ? undefined : value });
  };
  return (
    <Popover
      label="More filters"
      trapFocus
      trigger={(props) => (
        <Button {...props} variant="dashed" size="sm" icon="plus">
          Filter
        </Button>
      )}
    >
      <Stack gap={3}>
        <Field label="Sector">
          <Select
            options={options(distributionCategories(sectors.data), (v) => v, filters.sector)}
            value={filters.sector ?? ANY}
            onValueChange={set('sector')}
            disabled={sectors.isPending}
          />
        </Field>
        <Field label="Liquidity class">
          <Select
            options={options(
              distributionCategories(liquidity.data),
              liquidityLabel,
              filters.liquidity,
            )}
            value={filters.liquidity ?? ANY}
            onValueChange={set('liquidity')}
            disabled={liquidity.isPending}
          />
        </Field>
        <Field label="Security type">
          <Select
            options={options(distributionCategories(types.data), typeLabel, filters.type)}
            value={filters.type ?? ANY}
            onValueChange={set('type')}
            disabled={types.isPending}
          />
        </Field>
      </Stack>
    </Popover>
  );
}
