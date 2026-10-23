/**
 * The screeners as one list: your own (finalized and draft-only) and the site presets, narrowed
 * by a segment (All / Mine / Presets) and a search. A row is not expandable as a whole: it shows
 * the screener (kind, last run), its evidence (the strongest edge's record, opening in place to
 * one block per edge, one row at a time), today's picks (a link to the screener) and an edit
 * button (a preset is copied first). Python screeners are listed but built in code. Deleting asks first.
 */
import {
  Banner,
  Button,
  EmptyState,
  ExpandableTable,
  IconButton,
  Panel,
  SearchInput,
  SegmentedControl,
  Stack,
  StatusBadge,
  Text,
  VisuallyHidden,
  type ExpandableTableColumn,
  type ExpandableTableRow,
} from '@algotrade/ui';
import { useMemo, useState } from 'react';

import { ScreenerEvidenceCell, ScreenerEvidenceDetail } from '@/entities/edge';
import {
  DecisionBadge,
  useMyScreeners,
  useScreenerRuns,
  useScreeners,
  type ScreenerRunSummary,
} from '@/entities/screen';
import { CopyPresetDialog } from '@/features/screener-copy';
import { termHelp } from '@/features/guide-help';
import { DeleteScreenerDialog } from '@/features/screener-delete';

import { filterRows, SEGMENTS, toRows, type ListRow, type Segment } from '../model/rows';
import { changesOf } from '../model/summary';

export interface ScreenerListProps {
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
  { id: 'screener', label: withHelp('Screener', 'screener_column'), grow: 2, narrow: true },
  {
    id: 'evidence',
    label: withHelp('Evidence and edges', 'screener_track_record'),
    grow: 2.8,
    narrow: true,
  },
  { id: 'picks', label: withHelp('Picks today', 'screener_picks'), grow: 1.1, narrow: true },
  { id: 'actions', label: <VisuallyHidden>Actions</VisuallyHidden>, grow: 0.9, narrow: true },
];

export function ScreenerList({ onOpen, onEdit, onOpenEdge }: ScreenerListProps) {
  const configs = useScreeners();
  const mine = useMyScreeners();
  const runs = useScreenerRuns();
  const [segment, setSegment] = useState<Segment>('all');
  const [query, setQuery] = useState('');
  const [openId, setOpenId] = useState<string | null>(null);
  const [copying, setCopying] = useState<ListRow | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const rows = useMemo(
    () => filterRows(toRows(configs.data ?? [], mine.data ?? []), segment, query),
    [configs.data, mine.data, segment, query],
  );
  const failed = (configs.isError && !configs.data) || (mine.isError && !mine.data);
  const state = failed ? 'error' : configs.isPending || mine.isPending ? 'loading' : 'ready';
  return (
    <Stack gap={3}>
      <Stack direction="row" gap={3} align="center" wrap>
        <SegmentedControl
          aria-label="Show screeners"
          options={SEGMENTS}
          value={segment}
          onValueChange={setSegment}
        />
        <SearchInput
          aria-label="Search screeners"
          placeholder="Search screeners"
          value={query}
          onValueChange={setQuery}
        />
      </Stack>
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
          <EmptyState title="No screener matches" />
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

/** One row: the screener, its evidence, today's picks and the edit button; the evidence opens under it. */
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
        </>
      ),
      evidence: row.rules ? (
        <ScreenerEvidenceCell screenerId={row.id} open={open} onOpenChange={onOpenChange} />
      ) : (
        <Text size="sm" tone="muted">
          Built in code
        </Text>
      ),
      picks: run ? (
        <>
          <Button
            size="sm"
            variant="ghost"
            aria-label={`Open ${name}: ${String(run.picked)} picks`}
            onClick={() => {
              onOpen(row.id);
            }}
          >
            {`${String(run.picked)} ${run.picked === 1 ? 'pick' : 'picks'}`}
          </Button>
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
        '—'
      ),
      actions: row.rules ? (
        <Stack direction="row" gap={1} align="center">
          <IconButton
            icon="pencil"
            label={row.kind === 'mine' ? `Edit ${name}` : `Duplicate ${name} to edit`}
            onClick={() => {
              if (row.kind === 'mine') onEdit(row.id);
              else onDuplicate(row);
            }}
          />
          {row.kind === 'mine' && (
            <Button
              size="sm"
              variant="ghost"
              aria-label={`Delete ${row.id}`}
              onClick={() => {
                onDelete(row.id);
              }}
            >
              Delete
            </Button>
          )}
        </Stack>
      ) : null,
    },
  };
}
