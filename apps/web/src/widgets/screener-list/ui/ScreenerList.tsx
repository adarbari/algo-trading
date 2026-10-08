/**
 * The screeners as one list: your own (finalized and draft-only) and the site presets, narrowed
 * by a segment (All / Mine / Presets) and a search. A row summarises the screener (type, run,
 * track record, hits) and opens in place, one at a time, to its criteria, decisions, top hits and
 * actions. Python screeners are listed but built in code. Deleting asks first.
 */
import {
  Banner,
  EmptyState,
  ExpandableRow,
  Mono,
  Panel,
  SearchInput,
  SegmentedControl,
  Stack,
  StatusBadge,
  Text,
} from '@algotrade/ui';
import { useMemo, useState } from 'react';

import { ScreenerTrackChip } from '@/entities/edge';
import {
  useMyScreeners,
  useScreenerRuns,
  useScreeners,
  type ScreenerRunSummary,
} from '@/entities/screen';
import { CopyPresetDialog } from '@/features/screener-copy';
import { DeleteScreenerDialog } from '@/features/screener-delete';

import { filterRows, SEGMENTS, toRows, type ListRow, type Segment } from '../model/rows';
import { ScreenerDetail } from './ScreenerDetail';

export interface ScreenerListProps {
  /** Open a screener's results. */
  onOpen: (id: string) => void;
  /** Open a screener in the Builder (a new copy opens there: it has no run yet). */
  onEdit: (id: string) => void;
}

export function ScreenerList({ onOpen, onEdit }: ScreenerListProps) {
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
          <Stack gap={0} as="ul" aria-label="Screeners">
            {rows.map((row) => (
              <Stack as="li" key={`${row.kind}:${row.id}`} gap={0}>
                <ListEntry
                  row={row}
                  summary={runs.data?.byId.get(row.id)}
                  runsPending={runs.isPending}
                  open={openId === row.id}
                  onOpenChange={(open) => {
                    setOpenId(open ? row.id : null);
                  }}
                  onOpen={onOpen}
                  onEdit={onEdit}
                  onDelete={setDeleting}
                  onDuplicate={setCopying}
                />
              </Stack>
            ))}
          </Stack>
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

interface ListEntryProps {
  row: ListRow;
  summary: ScreenerRunSummary | undefined;
  runsPending: boolean;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onOpen: (id: string) => void;
  onEdit: (id: string) => void;
  onDelete: (id: string) => void;
  onDuplicate: (row: ListRow) => void;
}

/** One row: the summary cells over the lazily mounted detail. */
function ListEntry({ row, summary, runsPending, open, onOpenChange, ...actions }: ListEntryProps) {
  const run = summary?.latestRun ?? null;
  const noRun = !runsPending && row.rules && !run && !row.draft;
  return (
    <ExpandableRow
      title={<Mono>{row.id}</Mono>}
      badge={
        <StatusBadge tone={row.kind === 'mine' ? 'accent' : 'neutral'}>
          {row.kind === 'mine' ? 'Mine' : 'Preset'}
        </StatusBadge>
      }
      secondary={
        <>
          {row.error && (
            <StatusBadge tone="negative" title={row.error}>
              Does not resolve
            </StatusBadge>
          )}
          {row.draft && <StatusBadge tone="accent">Draft</StatusBadge>}
          {noRun && <StatusBadge tone="warning">No run today</StatusBadge>}
          {run && (
            <Text size="sm" tone="secondary">
              {`Run ${run.session}`}
            </Text>
          )}
          {row.rules && <ScreenerTrackChip screenerId={row.id} />}
        </>
      }
      essential={run ? <Mono>{String(run.picked)}</Mono> : <Text tone="muted">—</Text>}
      open={open}
      onOpenChange={onOpenChange}
    >
      <ScreenerDetail row={row} summary={summary} {...actions} />
    </ExpandableRow>
  );
}
