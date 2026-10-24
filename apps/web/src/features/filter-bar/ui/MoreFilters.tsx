/**
 * "More filters": find any catalogue feature by typing and filter on it (ADR 0082). The search is
 * the shared `FeatureCombobox` over the features the server lists for the surface (`filterFeatures`:
 * a feature the viewer's data licences do not cover is not listed; the phrasebook's words are in
 * each option's text so "liquid" finds dollar volume), with the catalogue's own summary under each
 * name. A pick starts a filter `feature:<field>` whose control is the one its kind gets, served by
 * the same definitions and counts as any other; it joins the URL when it gets a value. Declared
 * "more" filters of the surface are listed with it.
 */
import { Stack } from '@algotrade/ui';
import type { ReactNode } from 'react';

import {
  FEATURE_FILTER_PREFIX,
  useFilterFeatures,
  type FilterDefinition,
  type FilterFacets,
} from '@/entities/filter';
import { fieldOptions, FeatureCombobox, useFeatureCatalogue } from '@/entities/feature';

import type { FilterStateApi } from '../api/use-filter-state';
import type { LabelOf } from '../model/surface';
import { FilterControls, type GuideRef } from './FilterControls';

export interface MoreFiltersProps {
  surface: string;
  /** The definitions to show controls for: the declared "more" filters and the picked features'. */
  definitions: readonly FilterDefinition[];
  state: FilterStateApi;
  facets: FilterFacets | null | undefined;
  help: ((entry: GuideRef) => ReactNode) | undefined;
  labelOf: LabelOf | undefined;
  /** The catalogue fields picked and not yet given a value. */
  pending: readonly string[];
  onPick: (field: string) => void;
}

export function MoreFilters({
  surface,
  definitions,
  state,
  facets,
  help,
  labelOf,
  pending,
  onPick,
}: MoreFiltersProps) {
  const found = useFilterFeatures(surface, true);
  const catalogue = useFeatureCatalogue();
  const listed = new Map((found.data?.filterFeatures ?? []).map((f) => [f.name, f]));
  const inForce = new Set(state.filters.map((f) => f.id));
  const options = fieldOptions((catalogue.data ?? []).filter((f) => listed.has(f.name)))
    .filter((o) => !inForce.has(`${FEATURE_FILTER_PREFIX}${o.value}`) && !pending.includes(o.value))
    .map((o) => {
      const words = listed.get(o.value)?.synonyms ?? [];
      return words.length > 0
        ? { ...o, description: [o.description, words.join(', ')].filter(Boolean).join(' · ') }
        : o;
    });
  return (
    <Stack gap={3}>
      <FeatureCombobox
        aria-label="Find a filter"
        options={options}
        loading={found.isPending || catalogue.isPending}
        failed={found.isError || catalogue.isError}
        onPick={onPick}
      />
      <FilterControls
        definitions={definitions}
        state={state}
        facets={facets}
        help={help}
        labelOf={labelOf}
      />
    </Stack>
  );
}
