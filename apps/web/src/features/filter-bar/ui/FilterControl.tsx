/**
 * One filter's control in a group popover, chosen by the definition's `kind` (ADR 0082): a pick is
 * an `OptionList` with the server's counts, a select a `Select`, a toggle a `SegmentedControl`
 * (either / yes / no), a range a `RangeFilter` with the server's bins and unknown count, a window a
 * `WindowFilter`. The control only reads and writes the filter list; every count is served.
 */
import {
  OptionList,
  RangeFilter,
  SegmentedControl,
  Select,
  Stack,
  Text,
  WindowFilter,
} from '@algotrade/ui';
import type { ReactNode } from 'react';

import type { FilterDefinition, FilterFacets } from '@/entities/filter';

import type { FilterPatch, FilterState } from '../model/state';
import type { LabelOf } from '../model/surface';

type Facet = FilterFacets['items'][number];

export interface FilterControlProps {
  definition: FilterDefinition;
  /** The filter in force (undefined: none). */
  filter: FilterState | undefined;
  /** The server's counts for it (undefined: not served yet). */
  facet: Facet | undefined;
  /** Change the filter; an empty pick, an empty range or no window removes it. */
  onChange: (patch: FilterPatch) => void;
  onRemove: () => void;
  /** The help button of the filter's Guide entry. */
  help: ReactNode;
  /** The help button of the unknown-rows Guide entry, beside the range's unknown count. */
  unknownHelp: ReactNode;
  /** The caller's name for a stored value (a screener's name for its id). */
  labelOf?: LabelOf;
}

const ANY = '';
const TOGGLE_OPTIONS = [
  { value: ANY, label: 'Either' },
  { value: 'yes', label: 'Yes' },
  { value: 'no', label: 'No' },
] as const;

/** The choices of a pick or select: the definition's, else the values stored for the session (served in the facets). */
function choices(definition: FilterDefinition, facet: Facet | undefined, labelOf?: LabelOf) {
  const counts = new Map((facet?.options ?? []).map((o) => [o.value, o.count]));
  const named =
    definition.options.length > 0
      ? definition.options
      : (facet?.options ?? []).map((o) => ({ value: o.value, label: o.value }));
  return named.map((o) => ({
    ...o,
    label: labelOf?.(definition.id, o.value) ?? o.label,
    count: counts.get(o.value),
  }));
}

export function FilterControl({
  definition,
  filter,
  facet,
  onChange,
  onRemove,
  help,
  unknownHelp,
  labelOf,
}: FilterControlProps) {
  const values = filter?.values ?? [];
  let control: ReactNode = null;
  switch (definition.kind) {
    case 'PICK':
      control = (
        <OptionList
          label={definition.label}
          value={null}
          values={values}
          maxHeight="md"
          items={choices(definition, facet, labelOf).map((o) => ({
            id: o.value,
            title: o.label,
            ...(o.count !== undefined && { count: o.count }),
          }))}
          onSelect={(id) => {
            const next = values.includes(id) ? values.filter((v) => v !== id) : [...values, id];
            if (next.length === 0) onRemove();
            else onChange({ values: next });
          }}
        />
      );
      break;
    case 'SELECT':
      control = (
        <Select
          aria-label={definition.label}
          size="sm"
          value={values[0] ?? ANY}
          options={[
            { value: ANY, label: 'Any' },
            ...choices(definition, facet, labelOf).map((o) => ({ value: o.value, label: o.label })),
          ]}
          onValueChange={(value) => {
            if (value === ANY) onRemove();
            else onChange({ values: [value] });
          }}
        />
      );
      break;
    case 'TOGGLE':
      control = (
        <SegmentedControl
          aria-label={definition.label}
          size="sm"
          options={TOGGLE_OPTIONS}
          value={values[0] ?? ANY}
          onValueChange={(value) => {
            if (value === ANY) onRemove();
            else onChange({ values: [value] });
          }}
        />
      );
      break;
    case 'RANGE':
      control = (
        <RangeFilter
          label={definition.label}
          value={{
            ...(filter?.min !== undefined && { min: filter.min }),
            ...(filter?.max !== undefined && { max: filter.max }),
          }}
          bins={(facet?.bins ?? []).map((b) => ({ start: b.lo, end: b.hi, count: b.count }))}
          {...(facet && { unknownCount: facet.unknown })}
          unknownHelp={unknownHelp}
          onChange={(range) => {
            if (range.min === undefined && range.max === undefined) onRemove();
            else onChange({ min: range.min, max: range.max });
          }}
        />
      );
      break;
    case 'WINDOW': {
      const unit = definition.windowUnit === 'DAYS' ? 'days' : 'sessions';
      control = (
        <WindowFilter
          label={definition.label}
          unitLabel={definition.label}
          units={[{ value: unit, label: unit }]}
          value={{ amount: filter?.within?.amount ?? null, unit }}
          onChange={(next) => {
            if (next.amount === null) onRemove();
            else onChange({ within: { amount: next.amount, unit } });
          }}
        />
      );
      break;
    }
    case 'PERCENTILE':
      return null;
  }
  return (
    <Stack gap={2}>
      <Stack direction="row" gap={1} align="center">
        <Text weight="medium">{definition.label}</Text>
        {help}
      </Stack>
      {control}
    </Stack>
  );
}
