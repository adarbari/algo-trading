/**
 * The filter bar of any table, list or feed (ADR 0082, docs/ui/filtering.md): give it the surface
 * name, the filters in force (`useFilterState`) and the `facets` its read returned. It reads the
 * server's definitions (`filterSet`) and draws one button per group, each opening that group's
 * controls by kind; under the toolbar the applied chips (with the rows each removes), the
 * "N of M" line with Clear all and the caller's actions (Save view), and on a phone the one
 * Filters sheet ("Show N results"). Every name and count is the server's or the Guide's; the
 * caller supplies only the help button for a Guide entry (a feature cannot import another).
 */
import { Button, FilterBar, FilterChips, FilterGroupButton, Stack } from '@algotrade/ui';
import type { ReactNode } from 'react';

import {
  FILTER_GROUPS,
  useFilterSet,
  type FilterDefinition,
  type FilterFacets,
  type FilterGroup,
} from '@/entities/filter';

import type { FilterStateApi } from '../api/use-filter-state';
import { chipItems, countLine, groupCounts, type LabelOf } from '../model/surface';
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

export interface SurfaceFilterBarProps {
  /** The surface name (`ideas`): the key of its definitions. */
  surface: string;
  state: FilterStateApi;
  /** The counts the surface's read returned for the filters in force. */
  facets: FilterFacets | null | undefined;
  /** The help button of a Guide entry (the caller's `GuideHelp`); none: no help buttons. */
  help?: (entry: GuideRef) => ReactNode;
  /** The caller's `SearchInput`, for a surface that searches. */
  search?: ReactNode;
  /** Buttons after Clear all (Save view). */
  actions?: ReactNode;
  /** A name for a stored value the definitions do not label (a screener's name for its id). */
  labelOf?: LabelOf;
}

function Controls({
  definitions,
  state,
  facets,
  help,
  labelOf,
}: {
  definitions: readonly FilterDefinition[];
  state: FilterStateApi;
  facets: FilterFacets | null | undefined;
  help: SurfaceFilterBarProps['help'];
  labelOf: LabelOf | undefined;
}) {
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

export function SurfaceFilterBar({
  surface,
  state,
  facets,
  help,
  search = null,
  actions,
  labelOf,
}: SurfaceFilterBarProps) {
  const set = useFilterSet(surface);
  const definitions = set.data?.filterSet?.filters ?? [];
  const counts = groupCounts(state.filters, definitions);
  const inGroup = (group: FilterGroup) => definitions.filter((d) => d.group === group);
  const toolbar = FILTER_GROUPS.filter((g) => g.id !== 'MORE' && inGroup(g.id).length > 0);
  const more = inGroup('MORE');
  const count = countLine(facets);
  return (
    <FilterBar
      search={search}
      activeCount={state.filters.length}
      groups={toolbar.map((group) => (
        <FilterGroupButton
          key={group.id}
          label={group.label}
          activeCount={counts.get(group.id) ?? 0}
        >
          <Controls
            definitions={inGroup(group.id)}
            state={state}
            facets={facets}
            help={help}
            labelOf={labelOf}
          />
        </FilterGroupButton>
      ))}
      {...(more.length > 0 && {
        more: (
          <Controls
            definitions={more}
            state={state}
            facets={facets}
            help={help}
            labelOf={labelOf}
          />
        ),
      })}
      active={
        state.filters.length > 0 ? (
          <FilterChips
            items={chipItems(state.filters, definitions, facets, labelOf)}
            onToggle={state.toggle}
            onRemove={state.remove}
          />
        ) : null
      }
      {...(count !== undefined && { count })}
      {...(facets && { applyLabel: `Show ${String(facets.matched)} results` })}
      actions={
        <>
          {state.filters.length > 0 && (
            <Button size="sm" variant="ghost" onClick={state.clear}>
              Clear all
            </Button>
          )}
          {actions}
        </>
      }
    />
  );
}
