/**
 * The screeners as one list: your own (finalized and draft-only) and the site presets, narrowed
 * by the shared filter bar (ADR 0082: owner, last run, candidates, edges that list it, in the
 * URL's `f`) and a search over name and description, both answered by the server. Clicking a row (outside its own controls) opens the screener's page. A row shows
 * the screener (kind, last run), its evidence (the strongest edge's name first, opening in place
 * whenever it has edges to one block per edge, one row at a time), today's picks (a link to the
 * screener, "Not run" without a run: the one way into the screener page, for presets and Python
 * screeners too) and labelled actions: Edit criteria, Duplicate and Delete for yours, only
 * "Duplicate to edit" for a preset. Deleting asks first.
 */
import {
  Banner,
  Button,
  EmptyState,
  ActionGroup,
  ExpandableTable,
  LinkButton,
  Panel,
  SearchInput,
  Stack,
  StatusBadge,
  Text,
  type ActionItem,
  type ExpandableTableColumn,
  type ExpandableTableRow,
} from '@algotrade/ui';
import { useMemo, useState } from 'react';

import { useDebounced } from '@/shared/lib';

import { ScreenerEvidenceCell, ScreenerEvidenceDetail } from '@/entities/edge';
import {
  DecisionBadge,
  ScreenerDescription,
  useMyScreeners,
  useScreenerList,
  useScreenerRuns,
  useScreeners,
  type ScreenerRunSummary,
} from '@/entities/screen';
import { CopyPresetDialog } from '@/features/screener-copy';
import {
  SurfaceFilterBar,
  SurfaceZeroResults,
  useFilterState,
  type FilterSearch,
} from '@/features/filter-bar';
import { termHelp } from '@/features/guide-help';
import { DeleteScreenerDialog } from '@/features/screener-delete';

import { narrowRows, toRows, type ListRow } from '../model/rows';
import { changesOf } from '../model/summary';

/** The surface of the filter bar: its definitions are `config/site/filters/screeners.toml`. */
const SURFACE = 'screeners';

/** The list's search params: the filter bar's `f` and the search text `q`. */
export type ScreenerListSearch = FilterSearch & { q?: string };
export type ScreenerListSearchPatch = { f?: string | undefined; q?: string | undefined };

export interface ScreenerListProps {
  /** The filters in force and the search text (the URL's search params). */
  search: ScreenerListSearch;
  onSearchChange: (patch: ScreenerListSearchPatch) => void;
  /** Open a screener's results. */
  onOpen: (id: string) => void;
  /** Open a screener in the Builder (a new copy opens there: it has no run yet). */
  onEdit: (id: string) => void;
  /** Open an edge's evidence. */
  onOpenEdge: (edgeId: string) => void;
}

/** A header with the help button of the Guide term that explains the column (ADR 0051). */
const withHelp = (label: string, term: string) => (
  <Stack direction="row" gap={1} align="center">
    {label}
    {termHelp(term)}
  </Stack>
);

/** The four columns; all stay on a phone, where each row is a card. */
const COLUMNS: readonly ExpandableTableColumn[] = [
  {
    id: 'screener',
    label: withHelp('Screener and what it finds', 'screener_column'),
    grow: 2,
    narrow: true,
  },
  {
    id: 'evidence',
    label: withHelp('Evidence and edges', 'screener_track_record'),
    grow: 2.8,
    narrow: true,
  },
  { id: 'picks', label: withHelp('Picks today', 'screener_picks'), grow: 1.1, narrow: true },
  { id: 'actions', label: withHelp('Actions', 'screener_actions'), grow: 2.2, narrow: true },
];

export function ScreenerList({
  search,
  onSearchChange,
  onOpen,
  onEdit,
  onOpenEdge,
}: ScreenerListProps) {
  const configs = useScreeners();
  const mine = useMyScreeners();
  const runs = useScreenerRuns();
  const filters = useFilterState(search.f, (f) => {
    onSearchChange({ f });
  });
  const text = search.q ?? '';
  const narrowed = filters.filters.length > 0 || text.trim() !== '';
  const narrowing = useScreenerList(filters.filters, useDebounced(text, 250));
  const [openId, setOpenId] = useState<string | null>(null);
  const [copying, setCopying] = useState<ListRow | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const all = useMemo(() => toRows(configs.data ?? [], mine.data ?? []), [configs.data, mine.data]);
  const kept = narrowing.data?.ids ?? null;
  const rows = useMemo(() => narrowRows(all, narrowed ? kept : null), [all, narrowed, kept]);
  const failed = (configs.isError && !configs.data) || (mine.isError && !mine.data);
  const waiting = narrowed && narrowing.isPending && !narrowing.isError;
  const state = failed
    ? 'error'
    : configs.isPending || mine.isPending || waiting
      ? 'loading'
      : 'ready';
  const clearSearch = (
    <Button
      size="sm"
      variant="secondary"
      onClick={() => {
        onSearchChange({ q: undefined });
      }}
    >
      Clear the search
    </Button>
  );
  return (
    <Stack gap={3}>
      <SurfaceFilterBar
        surface={SURFACE}
        state={filters}
        facets={narrowing.data?.facets}
        help={(entry) => (entry.kind === 'term' ? termHelp(entry.id) : null)}
        search={
          <SearchInput
            aria-label="Search screeners"
            placeholder="Search screeners"
            value={text}
            onValueChange={(q) => {
              onSearchChange({ q: q || undefined });
            }}
          />
        }
      />
      {runs.isError && <Banner tone="warning">Today's runs failed to load.</Banner>}
      <Panel
        title="Screeners"
        flush
        state={state}
        loadingLabel="Loading screeners…"
        errorMessage="The screeners failed to load."
        onRetry={() => {
          void configs.refetch();
          void mine.refetch();
        }}
      >
        {rows.length === 0 ? (
          filters.filters.length > 0 ? (
            <Stack gap={2} align="start">
              <SurfaceZeroResults
                surface={SURFACE}
                state={filters}
                facets={narrowing.data?.facets}
              />
              {text && clearSearch}
            </Stack>
          ) : narrowed ? (
            <EmptyState compact title={`No screener matches "${text}"`} action={clearSearch} />
          ) : (
            <EmptyState title="No screener yet" />
          )
        ) : (
          <ExpandableTable
            label="Screeners"
            columns={COLUMNS}
            rowToggle={false}
            rows={rows.map((row) =>
              toTableRow(row, runs.data?.byId.get(row.id), runs.isPending, openId === row.id, {
                onOpenChange: (open) => {
                  setOpenId(open ? row.id : null);
                },
                onOpen,
                onEdit,
                onOpenEdge,
                onDelete: setDeleting,
                onDuplicate: setCopying,
              }),
            )}
          />
        )}
      </Panel>
      {copying && (
        <CopyPresetDialog
          preset={copying.id}
          own={copying.kind === 'mine'}
          open
          onOpenChange={(open) => {
            if (!open) setCopying(null);
          }}
          onCopied={(id) => {
            setCopying(null);
            onEdit(id);
          }}
        />
      )}
      {deleting && (
        <DeleteScreenerDialog
          screenerId={deleting}
          open
          onOpenChange={(open) => {
            if (!open) setDeleting(null);
          }}
          onDeleted={() => {
            setDeleting(null);
          }}
        />
      )}
    </Stack>
  );
}

interface RowActions {
  onOpenChange: (open: boolean) => void;
  onOpen: (id: string) => void;
  onEdit: (id: string) => void;
  onOpenEdge: (edgeId: string) => void;
  onDelete: (id: string) => void;
  onDuplicate: (row: ListRow) => void;
}

/** One row: the screener, its evidence, today's picks link and the actions; the evidence opens under it. */
function toTableRow(
  row: ListRow,
  summary: ScreenerRunSummary | undefined,
  runsPending: boolean,
  open: boolean,
  { onOpenChange, onOpen, onEdit, onOpenEdge, onDelete, onDuplicate }: RowActions,
): ExpandableTableRow {
  const run = summary?.latestRun ?? null;
  const noRun = !runsPending && row.rules && !run && !row.draft;
  const changes = changesOf(run?.changes ?? []);
  const paused = run !== null && run.picked === 0 && run.paused > 0;
  const name = summary?.name ?? row.id;
  return {
    id: `${row.kind}:${row.id}`,
    open,
    onOpenChange,
    onActivate: () => {
      onOpen(row.id);
    },
    detail: (
      <ScreenerEvidenceDetail
        screenerId={row.id}
        onOpenEdge={onOpenEdge}
        help={termHelp('record_how_to_read')}
      />
    ),
    cells: {
      screener: (
        <>
          <Text as="span" weight="medium">
            {name}{' '}
            <StatusBadge tone={row.kind === 'mine' ? 'accent' : 'neutral'}>
              {row.kind === 'mine' ? 'Mine' : 'Preset'}
            </StatusBadge>
            {row.error && (
              <>
                {' '}
                <StatusBadge tone="negative" title={row.error}>
                  Does not resolve
                </StatusBadge>
              </>
            )}
            {row.draft && (
              <>
                {' '}
                <StatusBadge tone="accent">Draft</StatusBadge>
              </>
            )}
          </Text>
          {summary?.description ? (
            <ScreenerDescription description={summary.description} />
          ) : row.kind === 'mine' && row.rules && summary && !runsPending ? (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                onEdit(row.id);
              }}
            >
              Add a description
            </Button>
          ) : null}
          {noRun ? (
            <StatusBadge tone="warning">No run today</StatusBadge>
          ) : paused ? (
            <Stack direction="row" gap={1} align="center">
              <DecisionBadge decision="PAUSED" />
              <Text size="xs" tone="muted">{`Last run ${run.session}`}</Text>
            </Stack>
          ) : run ? (
            <Text size="xs" tone="muted">{`Last run ${run.session}`}</Text>
          ) : null}
          {!row.rules && (
            <Text size="xs" tone="muted">
              Built in code
            </Text>
          )}
        </>
      ),
      evidence: (
        <ScreenerEvidenceCell screenerId={row.id} open={open} onOpenChange={onOpenChange} />
      ),
      picks: run ? (
        <>
          <LinkButton
            aria-label={`Open ${name}: ${String(run.picked)} picks`}
            onClick={() => {
              onOpen(row.id);
            }}
          >
            {`${String(run.picked)} ${run.picked === 1 ? 'pick' : 'picks'}`}
          </LinkButton>
          {changes && (
            <Text size="xs">
              <Text as="span" size="xs" tone="up">{`+${String(changes.added)}`}</Text>
              {' / '}
              <Text as="span" size="xs" tone="down">{`−${String(changes.dropped)}`}</Text>
            </Text>
          )}
          {run.paused > 0 && <Text size="xs" tone="muted">{`${String(run.paused)} paused`}</Text>}
        </>
      ) : (
        <LinkButton
          aria-label={`Open ${name}: not run`}
          onClick={() => {
            onOpen(row.id);
          }}
        >
          Not run
        </LinkButton>
      ),
      actions: (
        <RowActionGroup
          name={name}
          row={row}
          onEdit={onEdit}
          onDuplicate={onDuplicate}
          onDelete={onDelete}
        />
      ),
    },
  };
}

/**
 * The row's actions, labelled: yours get Edit criteria, Duplicate and Delete; a preset is never
 * changed in place, so it gets Duplicate to edit only; a screener built in code has none.
 */
function RowActionGroup({
  name,
  row,
  onEdit,
  onDuplicate,
  onDelete,
}: {
  name: string;
  row: ListRow;
  onEdit: (id: string) => void;
  onDuplicate: (row: ListRow) => void;
  onDelete: (id: string) => void;
}) {
  const mine = row.kind === 'mine';
  const actions: ActionItem[] = [
    ...(mine && row.rules
      ? [
          {
            id: 'edit',
            label: 'Edit criteria',
            icon: 'pencil' as const,
            onClick: () => {
              onEdit(row.id);
            },
          },
        ]
      : []),
    ...(row.rules
      ? [
          {
            id: 'duplicate',
            label: mine ? 'Duplicate' : 'Duplicate to edit',
            icon: 'copy' as const,
            onClick: () => {
              onDuplicate(row);
            },
          },
        ]
      : []),
    ...(mine
      ? [
          {
            id: 'delete',
            label: 'Delete',
            icon: 'trash' as const,
            variant: 'ghost' as const,
            onClick: () => {
              onDelete(row.id);
            },
          },
        ]
      : []),
  ];
  return actions.length === 0 ? null : (
    <ActionGroup label={`Actions of ${name}`} actions={actions} />
  );
}
