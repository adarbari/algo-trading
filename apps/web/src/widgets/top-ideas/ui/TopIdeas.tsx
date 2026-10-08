/**
 * "Top ideas": one row per ticker with every screener that picked it, ranked by the user's
 * screener priority then score (on the server), under the preset views and filter chips (the
 * page's search params). Tick tickers to compare them in Explore, or click one to open it there
 * with the screener that surfaced it.
 */
import { Button, DataTable, Panel, Stack, Text } from '@algotrade/ui';
import { useMemo, useState } from 'react';

import { helped } from '@/features/guide-help';
import { CompareIdeasButton, type IdeaCompareSearch } from '@/features/idea-compare';
import {
  activeFilterKeys,
  IDEA_VIEWS,
  useIdeas,
  type Idea,
  type IdeasSearch,
  type IdeasSearchPatch,
} from '@/entities/idea';

import { ideaColumns } from '../model/columns';
import { FILTER_TITLES, filterIdeas, optionLabel } from '../model/filters';

import { IdeaFilters } from './IdeaFilters';

export interface TopIdeasProps {
  /** The page's search params: the view in use and the filter chips. */
  search: IdeasSearch;
  onSearchChange: (patch: IdeasSearchPatch) => void;
  onCompare: (search: IdeaCompareSearch) => void;
  /** Open a ticker in Explore, with the screener (config id) that surfaced it. */
  onOpen: (symbol: string, via: string) => void;
  /** Open a screener's results (a screener chip in a row). */
  onOpenScreener: (screenerId: string) => void;
  /** Open the Screeners list (where a screener is run). */
  onScreeners: () => void;
}

export function TopIdeas({
  search,
  onSearchChange,
  onCompare,
  onOpen,
  onOpenScreener,
  onScreeners,
}: TopIdeasProps) {
  const ideas = useIdeas();
  const [selected, setSelected] = useState<string[]>([]);
  const all = useMemo(() => ideas.data?.ideas ?? [], [ideas.data]);
  const columns = useMemo(() => ideaColumns(all, onOpenScreener), [all, onOpenScreener]);
  const rows = useMemo(() => filterIdeas(all, search), [all, search]);
  const symbols = selected.flatMap((id) => {
    const symbol = all.find((idea) => idea.instrumentId === id)?.symbol;
    return symbol ? [symbol] : [];
  });

  // Nothing stored yet (`ideas: null`), or no screener ran for the session (each NOT_RUN):
  // not an error, an empty panel that says so.
  const ran = ideas.data?.screeners.some((s) => s.notRun === null) ?? false;
  const state =
    ideas.isError && !ideas.data
      ? 'error'
      : ideas.isPending
        ? 'loading'
        : ideas.data.session === null || !ran
          ? 'empty'
          : 'ready';

  const active = activeFilterKeys(search);
  const viewLabel = IDEA_VIEWS.find((v) => v.id === search.view)?.label;
  const because = [
    ...(viewLabel ? [viewLabel] : []),
    ...active.map((key) => `${FILTER_TITLES[key]}: ${optionLabel(all, key, search[key] ?? '')}`),
  ].join(' · ');
  const filteredEmpty = (
    <Stack gap={2} align="start">
      <Text tone="muted">{`No idea matches ${because}.`}</Text>
      <Button
        onClick={() => {
          onSearchChange({
            view: undefined,
            ...Object.fromEntries(active.map((key) => [key, undefined])),
          });
        }}
      >
        Clear filters
      </Button>
    </Stack>
  );

  return (
    <Stack gap={3}>
      <IdeaFilters ideas={all} search={search} onSearchChange={onSearchChange} />
      <Panel
        title="Top ideas · across all your screeners"
        description={
          ideas.data?.session
            ? `Session ${ideas.data.session} · ${rows.length} of ${all.length}`
            : undefined
        }
        flush
        state={state}
        loadingLabel="Loading ideas…"
        emptyMessage={
          <Stack gap={2} align="start">
            <Text tone="muted">
              {ideas.data?.session
                ? 'No screener has run for this session, so there are no ideas.'
                : 'No screener has run yet, so there are no ideas.'}
            </Text>
            <Button variant="primary" onClick={onScreeners}>
              Go to Screeners
            </Button>
          </Stack>
        }
        errorMessage="The ideas failed to load."
        onRetry={() => void ideas.refetch()}
        actions={<CompareIdeasButton symbols={symbols} onCompare={onCompare} />}
      >
        <DataTable<Idea>
          label="Top ideas"
          columns={columns.map(helped)}
          rows={rows}
          getRowId={(idea) => idea.instrumentId}
          getRowLabel={(idea) => idea.symbol ?? idea.instrumentId}
          defaultSort={{ columnId: 'rank', direction: 'asc' }}
          selectable
          selectedIds={selected}
          onSelectionChange={setSelected}
          onRowActivate={(idea) => {
            if (idea.symbol) onOpen(idea.symbol, idea.best.screenerId);
          }}
          canActivate={(idea) => Boolean(idea.symbol)}
          emptyMessage={
            all.length === 0 ? 'No screener picked anything in this session.' : filteredEmpty
          }
          visibleRows={14}
        />
      </Panel>
    </Stack>
  );
}
