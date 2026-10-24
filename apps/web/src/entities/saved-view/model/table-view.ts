/**
 * `useTableView(scope)`: the user's view of one table while they work with it. It starts from
 * their saved view (the default one, or the named one they pick); every change of columns,
 * sort or decisions is applied at once and saved into the view in use; "save as" names the
 * current choice as a new view, and a named view can be removed. Nothing saved: the lists are
 * empty and `decisions` is null, so the table applies its own defaults.
 *
 * A surface with a filter bar passes its `f` binding (ADR 0082): the view then saves the URL's
 * `f` with its columns and sort, and loading or switching to a view patches the URL's `f`
 * (filters of ids the surface no longer defines are dropped and listed in `droppedFilters`).
 */
import { useEffect, useRef, useState } from 'react';

import { useDeleteView, useSavedView, useSaveView } from '../api/views';

import { restorableFilters, type ViewContent } from './view';

type Edits = Partial<ViewContent>;

/** The surface's `f` search parameter: its current value and the writer (the route's). */
export interface FilterBinding {
  f: string | undefined;
  onChange: (next: string | undefined) => void;
  /** The filter ids the surface defines now; undefined: not loaded yet (nothing is dropped). */
  known?: readonly string[];
  /** Ids starting with it are defined too (`feature:`: made on the fly, the server gates them). */
  knownPrefix?: string;
  /**
   * The `f` for a view that holds none: nothing saved yet, or one saved with only the decisions
   * it showed (before filters existed; `decisions` is what it held, maybe none).
   */
  fallback?: (decisions: readonly string[]) => string | undefined;
}

export interface TableViewState {
  scope: string;
  /** The view in use (null: the default view). */
  name: string | null;
  /** The user's named views of the table, sorted. */
  names: readonly string[];
  /** Each named view with the `f` string it holds (one read lists them all). */
  named: readonly { name: string; filters: string }[];
  /** The saved view has been read, and with a filter binding its `f` restored (the table can ask for its rows). */
  ready: boolean;
  columns: readonly string[];
  /** The columns added back on a narrow table. */
  narrowColumns: readonly string[];
  sort: string | null;
  /** The decisions shown; null: none chosen (the table's default). */
  decisions: readonly string[] | null;
  /** The filter ids saved in the view in use that the surface no longer defines. */
  droppedFilters: readonly string[];
  /** Apply and save a change to the view in use. */
  change: (next: Edits) => void;
  /** Switch to another of the views (null: the default); unsaved choices are dropped. */
  select: (name: string | null) => void;
  /** Save the current choice as the view `name` (replacing one of that name), then use it. */
  saveAs: (name: string, onDone?: () => void) => void;
  /** Remove the named view `target` (default: the one in use; removing that goes back to the default view). */
  remove: (target?: string) => void;
  saving: boolean;
  removing: boolean;
  /** Why the last save was refused. */
  error: unknown;
}

/**
 * `enabled` false (a menu not opened yet) reads nothing and restores nothing: no request fires
 * on a page's load for a view nobody asked for; turning it on later reads the views.
 */
export function useTableView(
  scope: string,
  filters?: FilterBinding,
  enabled = true,
): TableViewState {
  const [name, setName] = useState<string | null>(null);
  const [edits, setEdits] = useState<Edits>({});
  const saved = useSavedView(scope, name, enabled);
  const save = useSaveView(scope);
  const removal = useDeleteView(scope);
  const view = saved.data;
  const restore = useRef<'initial' | 'switched' | null>(enabled ? 'initial' : null);
  // With a filter binding the table waits for the view's `f` to be in the URL before it reads.
  const [restoredF, setRestoredF] = useState(false);
  const restored = restorableFilters(view?.filters ?? '', filters?.known, filters?.knownPrefix);
  const decided = view?.saved ? view.decisions : [];
  const seeded =
    restored.f ||
    (!view || (!view.filters && (!view.saved || decided.length > 0))
      ? (filters?.fallback?.(decided) ?? '')
      : '');
  const onFilters = filters?.onChange;
  const urlFilters = filters?.f;
  const known = filters?.known !== undefined;
  useEffect(() => {
    if (!onFilters || saved.isPending || !restore.current || !known) return;
    // The URL's own `f` (a shared link) wins over the default view's on first load.
    if (restore.current === 'switched' || !urlFilters) onFilters(seeded || undefined);
    restore.current = null;
    setRestoredF(true);
  }, [saved.isPending, onFilters, urlFilters, known, seeded]);
  const current: ViewContent = {
    columns: edits.columns ?? view?.columns ?? [],
    narrowColumns: edits.narrowColumns ?? view?.narrowColumns ?? [],
    sort: edits.sort !== undefined ? edits.sort : (view?.sort ?? null),
    decisions: edits.decisions ?? (view?.saved ? view.decisions : []),
    filters: filters ? (filters.f ?? '') : (view?.filters ?? ''),
  };
  const select = (next: string | null) => {
    restore.current = 'switched';
    setRestoredF(false);
    setName(next);
    setEdits({});
  };
  return {
    scope,
    name,
    names: view?.names ?? [],
    named: view?.named ?? [],
    ready: enabled && !saved.isPending && (!filters || restoredF),
    columns: current.columns,
    narrowColumns: current.narrowColumns,
    sort: current.sort,
    decisions:
      edits.decisions ?? (view?.saved && view.decisions.length > 0 ? view.decisions : null),
    droppedFilters: restored.dropped,
    change: (next) => {
      setEdits((now) => ({ ...now, ...next }));
      save.mutate({ name, view: { ...current, ...next } });
    },
    select,
    saveAs: (next, onDone) => {
      save.mutate(
        { name: next, view: current },
        {
          onSuccess: () => {
            select(next);
            onDone?.();
          },
        },
      );
    },
    remove: (target = name ?? undefined) => {
      if (target === undefined) return;
      removal.mutate(target, {
        onSuccess: () => {
          if (target === name) select(null);
        },
      });
    },
    saving: save.isPending,
    removing: removal.isPending,
    error: save.error,
  };
}
