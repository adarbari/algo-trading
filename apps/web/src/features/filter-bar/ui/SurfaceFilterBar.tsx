/**
 * The filter bar of any table, list or feed (ADR 0082, docs/ui/filtering.md): give it the surface
 * name, the filters in force (`useFilterState`) and the `facets` its read returned. It reads the
 * server's definitions (`filterSet`) and draws one button per group, each opening that group's
 * controls by kind; under the toolbar the applied chips (with the rows each removes), the
 * "N of M" line with Clear all and the caller's actions (Save view), and on a phone the one
 * Filters sheet ("Show N results"). Every name and count is the server's or the Guide's; the
 * caller supplies only the help button for a Guide entry (a feature cannot import another).
 */
import { Button, FilterBar, FilterChips, FilterGroupButton } from '@algotrade/ui';
import { lazy, Suspense, useState, type ReactNode } from 'react';

import {
  FEATURE_FILTER_PREFIX,
  FILTER_GROUPS,
  useFilterSet,
  type FilterDefinition,
  type FilterFacets,
  type FilterGroup,
} from '@/entities/filter';

import { surfaceScope, useTableView, type TableViewState } from '@/entities/saved-view';

import type { FilterStateApi } from '../api/use-filter-state';
import { chipItems, countLine, groupCounts, type LabelOf } from '../model/surface';
import { FilterControls, type GuideRef } from './FilterControls';
import { ViewsMenu } from './ViewsMenu';

// The search and the catalogue behind it load when "More filters" first opens.
const MoreFilters = lazy(() => import('./MoreFilters').then((m) => ({ default: m.MoreFilters })));

export { parseGuideRef, type GuideRef } from './FilterControls';

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
  /**
   * The Views menu (saved views, ADR 0082): `true` (the bar keeps the user's views of this
   * surface, scope `surface:<name>`), a scope, or the `useTableView` state a page that also saves
   * columns and sort in its view already holds. None: no Views button.
   */
  views?: boolean | string | TableViewState;
}

/** The Views menu of a scope the bar keeps itself. */
function ScopedViews({
  scope,
  state,
  known,
  definitions,
  labelOf,
}: {
  scope: string;
  state: FilterStateApi;
  known: readonly string[] | undefined;
  definitions: readonly FilterDefinition[];
  labelOf: LabelOf | undefined;
}) {
  const view = useTableView(scope, {
    f: state.f,
    onChange: state.replace,
    ...(known && { known }),
  });
  return <ViewsMenu view={view} state={state} definitions={definitions} labelOf={labelOf} />;
}

export function SurfaceFilterBar({
  surface,
  state,
  facets,
  help,
  search = null,
  actions,
  labelOf,
  views,
}: SurfaceFilterBarProps) {
  const [pending, setPending] = useState<readonly string[]>([]);
  const fields = [
    ...state.filters
      .filter((f) => f.id.startsWith(FEATURE_FILTER_PREFIX))
      .map((f) => f.id.slice(FEATURE_FILTER_PREFIX.length)),
    ...pending,
  ];
  const set = useFilterSet(surface, [...new Set(fields)]);
  const definitions = set.data?.filterSet?.filters ?? [];
  const searchable = set.data?.filterSet?.searchable ?? false;
  // A saved view keeps the filters the surface still defines: its own and the picked features.
  const known = set.data?.filterSet
    ? [
        ...definitions.map((d) => d.id),
        ...state.filters.map((f) => f.id).filter((id) => id.startsWith(FEATURE_FILTER_PREFIX)),
      ]
    : set.isError
      ? []
      : undefined;
  const counts = groupCounts(state.filters, definitions);
  const inGroup = (group: FilterGroup) => definitions.filter((d) => d.group === group);
  const toolbar = FILTER_GROUPS.filter((g) => g.id !== 'MORE' && inGroup(g.id).length > 0);
  const more = inGroup('MORE');
  const count = countLine(facets);
  return (
    <FilterBar
      search={search}
      activeCount={state.filters.length}
      groups={
        <>
          {toolbar.map((group) => (
            <FilterGroupButton
              key={group.id}
              label={group.label}
              activeCount={counts.get(group.id) ?? 0}
            >
              <FilterControls
                definitions={inGroup(group.id)}
                state={state}
                facets={facets}
                help={help}
                labelOf={labelOf}
              />
            </FilterGroupButton>
          ))}
          {views !== undefined &&
            views !== false &&
            (typeof views === 'string' || views === true ? (
              <ScopedViews
                scope={views === true ? surfaceScope(surface) : views}
                state={state}
                known={known}
                definitions={definitions}
                labelOf={labelOf}
              />
            ) : (
              <ViewsMenu view={views} state={state} definitions={definitions} labelOf={labelOf} />
            ))}
        </>
      }
      {...(searchable
        ? {
            more: (
              <Suspense fallback={null}>
                <MoreFilters
                  surface={surface}
                  definitions={more}
                  state={state}
                  facets={facets}
                  help={help}
                  labelOf={labelOf}
                  pending={pending}
                  onPick={(field) => {
                    setPending((now) => [...now, field]);
                  }}
                />
              </Suspense>
            ),
          }
        : more.length > 0 && {
            more: (
              <FilterControls
                definitions={more}
                state={state}
                facets={facets}
                help={help}
                labelOf={labelOf}
              />
            ),
          })}
      moreLabel="More filters"
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
