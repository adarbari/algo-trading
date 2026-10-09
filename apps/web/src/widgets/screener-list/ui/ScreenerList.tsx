/**
 * The screeners as one list: your own (finalized and draft-only) and the site presets, narrowed
 * by a segment (All / Mine / Presets) and a search. A row summarises the screener (type, run,
 * track record, hits) and opens in place, one at a time, to its criteria, decisions, top hits and
 * actions. Python screeners are listed but built in code. Deleting asks first.
 */
import {
  Banner,
  EmptyState,
  ExpandableTable,
  Panel,
  SearchInput,
  SegmentedControl,
  Stack,
  StackedBar,
  StatusBadge,
  Text,
  TextLink,
  type ExpandableTableColumn,
  type ExpandableTableRow,
} from '@algotrade/ui';
import { lazy, Suspense, useMemo, useState } from 'react';

import { ScreenerEdgeName, ScreenerRecord } from '@/entities/edge';
import {
  DecisionBadge,
  useMyScreeners,
  useScreenerRuns,
  useScreeners,
  type ScreenerRunSummary,
} from '@/entities/screen';
import { playbookPath } from '@/entities/guide';
import { CopyPresetDialog } from '@/features/screener-copy';
import { DeleteScreenerDialog } from '@/features/screener-delete';

import { filterRows, SEGMENTS, toRows, type ListRow, type Segment } from '../model/rows';
import { changesOf, decisionSegments } from '../model/summary';

/** The opened row loads on demand: its own chunk, so the list's first paint stays small. */
const ScreenerDetail = lazy(() =>
  import('./ScreenerDetail').then((m) => ({ default: m.ScreenerDetail })),
);

export interface ScreenerListProps {
  /** Open a screener's results. */
  onOpen: (id: string) => void;
  /** Open a screener in the Builder (a new copy opens there: it has no run yet). */
  onEdit: (id: string) => void;
  /** Open a hit's ticker in Explore, arriving through the screener. */
  onOpenTicker: (symbol: string, via: string) => void;
  /** Open an edge's evidence. */
  onOpenEdge: (edgeId: string) => void;
}

/**
 * The columns. A 30-day pick sparkline (`Screener.pickHistory`) slots in between the track
 * record and the last run once the API serves it, with a `Sparkline` cell.
 */
const COLUMNS: readonly ExpandableTableColumn[] = [
  { id: 'screener', label: 'Screener', grow: 2.2, narrow: true },
  { id: 'picks', label: 'Picks today', align: 'end', narrow: true },
  { id: 'decisions', label: 'Decisions', grow: 1.2 },
  { id: 'record', label: 'Track record', grow: 1.6, narrow: true },
  { id: 'last', label: 'Last run' },
];

export function ScreenerList({ onOpen, onEdit, onOpenTicker, onOpenEdge }: ScreenerListProps) {
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
            rows={rows.map((row) =>
              toTableRow(row, runs.data?.byId.get(row.id), runs.isPending, openId === row.id, {
                onOpenChange: (open) => {
                  setOpenId(open ? row.id : null);
                },
                onOpen,
                onEdit,
                onOpenTicker,
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
  onOpenTicker: (symbol: string, via: string) => void;
  onOpenEdge: (edgeId: string) => void;
  onDelete: (id: string) => void;
  onDuplicate: (row: ListRow) => void;
}

/** One row: the summary cells, and the lazily mounted detail. */
function toTableRow(
  row: ListRow,
  summary: ScreenerRunSummary | undefined,
  runsPending: boolean,
  open: boolean,
  { onOpenChange, ...actions }: RowActions,
): ExpandableTableRow {
  const run = summary?.latestRun ?? null;
  const noRun = !runsPending && row.rules && !run && !row.draft;
  const changes = changesOf(run?.changes ?? []);
  const segments = decisionSegments(run?.decisions ?? []);
  const paused = run !== null && run.picked === 0 && run.paused > 0;
  const none = '—';
  return {
    id: `${row.kind}:${row.id}`,
    open,
    onOpenChange,
    detail: (
      <Suspense
        fallback={
          <Text size="sm" tone="muted">
            Loading…
          </Text>
        }
      >
        <ScreenerDetail
          row={row}
          summary={summary}
          {...actions}
          playbook={
            <TextLink href={playbookPath(row.id)} icon="book" size="sm">
              Playbook
            </TextLink>
          }
        />
      </Suspense>
    ),
    cells: {
      screener: (
        <>
          <Text as="span" weight="medium">
            {summary?.name ?? row.id}{' '}
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
          {row.rules ? <ScreenerEdgeName screenerId={row.id} /> : null}
        </>
      ),
      picks: run ? (
        <>
          <Text as="span" weight="medium" mono>
            {String(run.picked)}
            {changes && (
              <>
                {' '}
                <Text size="xs" tone="up">{`+${String(changes.added)}`}</Text>{' '}
                <Text size="xs" tone="down">{`−${String(changes.dropped)}`}</Text>
              </>
            )}
          </Text>
          {run.paused > 0 && <Text size="xs" tone="muted">{`${String(run.paused)} paused`}</Text>}
        </>
      ) : (
        none
      ),
      decisions: run ? (
        <>
          <StackedBar
            label={`Decisions of ${row.id}`}
            size="sm"
            showLegend={false}
            segments={segments}
            emptyMessage="No picks"
          />
          <Text size="xs" tone="muted">
            {segments.map((s) => `${String(s.value)} ${s.label.toLowerCase()}`).join(' · ')}
          </Text>
        </>
      ) : (
        none
      ),
      record: row.rules ? <ScreenerRecord screenerId={row.id} /> : none,
      last: noRun ? (
        <StatusBadge tone="warning">No run today</StatusBadge>
      ) : paused ? (
        <>
          <DecisionBadge decision="PAUSED" />
          <Text size="xs" tone="muted">
            {run.session}
          </Text>
        </>
      ) : run ? (
        <Text size="sm" tone="muted">
          {run.session}
        </Text>
      ) : (
        none
      ),
    },
  };
}
