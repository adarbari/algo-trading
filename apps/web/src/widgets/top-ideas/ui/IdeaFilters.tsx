/**
 * The bar above the ideas table: the preset views (one is in use, "Top today" by default) and
 * the filter chips. A filter in force is a removable chip; one not in force is a dashed
 * "+ Name" button that opens its values; "Clear filters" shows only while one is in force.
 * Everything is the page's search params, so a view of the table is a link.
 */
import { Button, Chip, OptionList, Popover, Stack } from '@algotrade/ui';
import { useState } from 'react';

import {
  activeFilterKeys,
  IDEA_FILTER_KEYS,
  IDEA_VIEWS,
  type Idea,
  type IdeaFilterKey,
  type IdeasSearch,
  type IdeasSearchPatch,
} from '@/entities/idea';

import { FILTER_TITLES, filterOptions, optionLabel } from '../model/filters';

export interface IdeaFiltersProps {
  ideas: readonly Idea[];
  search: IdeasSearch;
  onSearchChange: (patch: IdeasSearchPatch) => void;
}

function AddFilter({
  ideas,
  filter,
  onPick,
}: {
  ideas: readonly Idea[];
  filter: IdeaFilterKey;
  onPick: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const options = filterOptions(ideas, filter);
  return (
    <Popover
      label={FILTER_TITLES[filter]}
      open={open}
      onOpenChange={setOpen}
      width="auto"
      padding="none"
      trigger={(props) => (
        <Button {...props} variant="dashed" size="sm" icon="plus">
          {FILTER_TITLES[filter]}
        </Button>
      )}
    >
      <OptionList
        label={FILTER_TITLES[filter]}
        value={null}
        maxHeight="md"
        items={options.map((o) => ({ id: o.value, title: o.label }))}
        onSelect={(value) => {
          onPick(value);
          setOpen(false);
        }}
      />
    </Popover>
  );
}

export function IdeaFilters({ ideas, search, onSearchChange }: IdeaFiltersProps) {
  const active = activeFilterKeys(search);
  const view = search.view ?? 'top';
  return (
    <Stack gap={2}>
      <Stack direction="row" gap={1} align="center" wrap>
        {IDEA_VIEWS.map((v) => (
          <Chip
            key={v.id}
            label={v.label}
            selected={view === v.id}
            onSelectedChange={() => {
              onSearchChange({ view: v.id });
            }}
          />
        ))}
      </Stack>
      <Stack direction="row" gap={1} align="center" wrap>
        {active.map((key) => (
          <Chip
            key={key}
            label={`${FILTER_TITLES[key]}: ${optionLabel(ideas, key, search[key] ?? '')}`}
            onRemove={() => {
              onSearchChange({ [key]: undefined });
            }}
          />
        ))}
        {IDEA_FILTER_KEYS.filter((key) => !active.includes(key)).map((key) => (
          <AddFilter
            key={key}
            ideas={ideas}
            filter={key}
            onPick={(value) => {
              onSearchChange({ [key]: value });
            }}
          />
        ))}
        {active.length > 0 ? (
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              onSearchChange(Object.fromEntries(active.map((key) => [key, undefined])));
            }}
          >
            Clear filters
          </Button>
        ) : null}
      </Stack>
    </Stack>
  );
}
