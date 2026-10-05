/**
 * `useTableView(scope)`: the user's view of one table while they work with it. It starts from
 * their saved view (the default one, or the named one they pick); every change of columns,
 * sort or decisions is applied at once and saved into the view in use; "save as" names the
 * current choice as a new view, and a named view can be removed. Nothing saved: the lists are
 * empty and `decisions` is null, so the table applies its own defaults.
 */
import { useState } from 'react';

import { useDeleteView, useSavedView, useSaveView } from '../api/views';

import type { ViewContent } from './view';

type Edits = Partial<ViewContent>;

export interface TableViewState {
  scope: string;
  /** The view in use (null: the default view). */
  name: string | null;
  /** The user's named views of the table, sorted. */
  names: readonly string[];
  /** The saved view has been read (the table can ask for its rows). */
  ready: boolean;
  columns: readonly string[];
  sort: string | null;
  /** The decisions shown; null: none chosen (the table's default). */
  decisions: readonly string[] | null;
  /** Apply and save a change to the view in use. */
  change: (next: Edits) => void;
  /** Switch to another of the views (null: the default); unsaved choices are dropped. */
  select: (name: string | null) => void;
  /** Save the current choice as the view `name` (replacing one of that name), then use it. */
  saveAs: (name: string, onDone?: () => void) => void;
  /** Remove the named view in use and go back to the default view. */
  remove: () => void;
  saving: boolean;
  removing: boolean;
  /** Why the last save was refused. */
  error: unknown;
}

export function useTableView(scope: string): TableViewState {
  const [name, setName] = useState<string | null>(null);
  const [edits, setEdits] = useState<Edits>({});
  const saved = useSavedView(scope, name);
  const save = useSaveView(scope);
  const removal = useDeleteView(scope);
  const view = saved.data;
  const current: ViewContent = {
    columns: edits.columns ?? view?.columns ?? [],
    sort: edits.sort !== undefined ? edits.sort : (view?.sort ?? null),
    decisions: edits.decisions ?? (view?.saved ? view.decisions : []),
  };
  const select = (next: string | null) => {
    setName(next);
    setEdits({});
  };
  return {
    scope,
    name,
    names: view?.names ?? [],
    ready: !saved.isPending,
    columns: current.columns,
    sort: current.sort,
    decisions:
      edits.decisions ?? (view?.saved && view.decisions.length > 0 ? view.decisions : null),
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
    remove: () => {
      if (name === null) return;
      removal.mutate(name, {
        onSuccess: () => {
          select(null);
        },
      });
    },
    saving: save.isPending,
    removing: removal.isPending,
    error: save.error,
  };
}
