/**
 * The bar above the ideas table: the preset views and the filter chips, both design-system
 * components fed from the page's search params (so a view of the table is a link).
 */
import { FilterChips, Stack, ViewChips } from '@algotrade/ui';

import {
  IDEA_FILTER_KEYS,
  IDEA_VIEWS,
  type Idea,
  type IdeaFilterKey,
  type IdeasSearch,
  type IdeasSearchPatch,
} from '@/entities/idea';

import { FILTER_TITLES, filterOptions } from '../model/filters';

export interface IdeaFiltersProps {
  ideas: readonly Idea[];
  search: IdeasSearch;
  onSearchChange: (patch: IdeasSearchPatch) => void;
}

const isKey = (id: string): id is IdeaFilterKey => IDEA_FILTER_KEYS.some((key) => key === id);

export function IdeaFilters({ ideas, search, onSearchChange }: IdeaFiltersProps) {
  return (
    <Stack gap={2}>
      <ViewChips
        views={IDEA_VIEWS.map((v) => ({ value: v.id, label: v.label }))}
        value={search.view ?? 'top'}
        onValueChange={(view) => {
          onSearchChange({ view });
        }}
      />
      <FilterChips
        filters={IDEA_FILTER_KEYS.map((key) => ({
          id: key,
          label: FILTER_TITLES[key],
          options: filterOptions(ideas, key),
        }))}
        values={Object.fromEntries(IDEA_FILTER_KEYS.map((key) => [key, search[key]]))}
        onChange={(id, value) => {
          if (isKey(id)) onSearchChange({ [id]: value });
        }}
        onClear={() => {
          onSearchChange(Object.fromEntries(IDEA_FILTER_KEYS.map((key) => [key, undefined])));
        }}
      />
    </Stack>
  );
}
