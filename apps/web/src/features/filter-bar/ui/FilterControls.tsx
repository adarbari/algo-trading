/**
 * The controls of a list of filter definitions, one `FilterControl` each, wired to the filter
 * state: what a group popover (and "More filters") holds.
 */
import { Stack } from '@algotrade/ui';
import type { ReactNode } from 'react';

import type { FilterDefinition, FilterFacets } from '@/entities/filter';

import type { FilterStateApi } from '../api/use-filter-state';
import type { LabelOf } from '../model/surface';
import { FilterControl } from './FilterControl';

/** A Guide entry reference as the definitions carry it (`term:filter_decision`). */
export interface GuideRef {
  kind: string;
  id: string;
}

/** The Guide term that says what an unknown row is (shown beside a range's unknown count). */
const UNKNOWN_ROWS: GuideRef = { kind: 'term', id: 'filter_unknown_rows' };

export function parseGuideRef(ref: string): GuideRef {
  const at = ref.indexOf(':');
  return at < 0 ? { kind: 'term', id: ref } : { kind: ref.slice(0, at), id: ref.slice(at + 1) };
}

export interface FilterControlsProps {
  definitions: readonly FilterDefinition[];
  state: FilterStateApi;
  facets: FilterFacets | null | undefined;
  /** The help button of a Guide entry (the caller's `GuideHelp`). */
  help: ((entry: GuideRef) => ReactNode) | undefined;
  labelOf: LabelOf | undefined;
}

export function FilterControls({ definitions, state, facets, help, labelOf }: FilterControlsProps) {
  return (
    <Stack gap={3}>
      {definitions.map((definition) => (
        <FilterControl
          key={definition.id}
          definition={definition}
          filter={state.filters.find((f) => f.id === definition.id)}
          facet={facets?.items.find((f) => f.id === definition.id)}
          onChange={(patch) => {
            state.set(definition.id, patch);
          }}
          onRemove={() => {
            state.remove(definition.id);
          }}
          help={help?.(parseGuideRef(definition.guide))}
          unknownHelp={help?.(UNKNOWN_ROWS)}
          {...(labelOf && { labelOf })}
        />
      ))}
    </Stack>
  );
}
