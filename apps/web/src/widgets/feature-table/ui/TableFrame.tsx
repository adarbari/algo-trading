/**
 * The frame every table of the widget shares: a panel (title, actions, states), the session
 * notes (a stale session, nightly tables missing for it, a universe snapshot from after it; for a
 * screener's run, the run's own coverage: a PARTIAL run and the tables it ran without),
 * the caller's header (filters), and the design system's `DataTable` over `TableRow`s with a
 * toolbar: the summary, the pager (server paging) and the caller's controls (column picker,
 * views). The columns are a `ColumnPlan` from the factories (ADR 0038); a field column's
 * header gets its help button (`features/guide-help`, ADR 0051).
 */
import {
  Banner,
  Box,
  DataTable,
  IconButton,
  Panel,
  Stack,
  Text,
  type DataTableProps,
  type PanelProps,
} from '@algotrade/ui';
import type { ReactNode } from 'react';

import { isStale } from '@/entities/explore';
import type { ColumnPlan, TableRow } from '@/entities/feature';
import { helped } from '@/features/guide-help';

import { missingTables } from '../model/plan';

/** A screener run's own coverage, as its run record says (not the session as read now). */
export interface RunNotes {
  session: string;
  partial: boolean;
  /** The tables that had no rows when it ran. */
  missing: readonly string[];
}

export interface SessionNotes {
  session: string;
  missing: readonly string[];
  preSnapshot: boolean;
  /** The run the rows come from (absent: not a run). */
  run?: RunNotes | null | undefined;
}

export interface Pager {
  page: number;
  pages: number;
  onPage: (page: number) => void;
}

export interface TableFrameProps {
  panel: Omit<PanelProps, 'children' | 'flush'>;
  /** The session the rows are for, with what is missing for it (null: no notes). */
  notes?: SessionNotes | null | undefined;
  /** Above the table: filters. */
  header?: ReactNode;
  summary: string;
  /** Server paging; null: one page. */
  pager?: Pager | null | undefined;
  /** Toolbar controls after the pager (the column picker, the view controls). */
  controls?: ReactNode;
  grid: Omit<
    DataTableProps<TableRow>,
    'toolbar' | 'getRowId' | 'getRowLabel' | 'rowLines' | 'columns'
  > &
    Partial<Pick<DataTableProps<TableRow>, 'getRowId'>> & { columns: ColumnPlan };
}

const count = (n: number) => n.toLocaleString('en-US');

function Notes({ notes }: { notes: SessionNotes }) {
  const missing = missingTables(notes.missing);
  return (
    <>
      {isStale(notes.session) ? (
        <Banner asOf={notes.session}>
          The latest stored session is old: a nightly run may have been missed.
        </Banner>
      ) : null}
      {missing.length > 0 || notes.preSnapshot ? (
        <Banner tone="warning" title="Partial data">
          {notes.preSnapshot ? 'The universe snapshot is from after this session. ' : ''}
          {missing.length > 0
            ? `Not stored for ${notes.session}: ${missing.join(', ')}. Values from these tables read Unknown.`
            : ''}
        </Banner>
      ) : null}
      {notes.run && runShows(notes.run) ? <RunBanner run={notes.run} /> : null}
    </>
  );
}

function runShows(run: RunNotes): boolean {
  return run.partial || run.missing.length > 0;
}

function RunBanner({ run }: { run: RunNotes }) {
  const missing = missingTables(run.missing);
  return (
    <Banner tone="warning" title="Partial run">
      {missing.length > 0
        ? `The run for ${run.session} is PARTIAL, run without ${missing.join(', ')}; Run now re-runs it.`
        : `The run for ${run.session} is PARTIAL; Run now re-runs it.`}
    </Banner>
  );
}

function shows(notes: SessionNotes | null | undefined): notes is SessionNotes {
  return (
    !!notes &&
    (isStale(notes.session) ||
      notes.missing.length > 0 ||
      notes.preSnapshot ||
      (!!notes.run && runShows(notes.run)))
  );
}

export function TableFrame({
  panel,
  notes,
  header,
  summary,
  pager,
  controls,
  grid,
}: TableFrameProps) {
  return (
    <Panel {...panel} flush>
      <Stack gap={0}>
        {header || shows(notes) ? (
          <Box padding={3}>
            <Stack gap={2}>
              {shows(notes) ? <Notes notes={notes} /> : null}
              {header}
            </Stack>
          </Box>
        ) : null}
        <DataTable<TableRow>
          getRowId={(row) => row.symbol}
          {...grid}
          columns={grid.columns.map(helped)}
          getRowLabel={(row) => row.symbol}
          rowLines={2}
          toolbar={
            <Stack direction="row" gap={2} align="center" wrap>
              <Text size="sm" tone="muted">
                {summary}
              </Text>
              {pager && pager.pages > 1 ? (
                <Stack direction="row" gap={1} align="center">
                  <IconButton
                    icon="chevron-left"
                    label="Previous page"
                    size="sm"
                    disabled={pager.page <= 1}
                    onClick={() => {
                      pager.onPage(pager.page - 1);
                    }}
                  />
                  <Text size="sm" tone="muted" numeric>
                    Page {count(pager.page)} of {count(pager.pages)}
                  </Text>
                  <IconButton
                    icon="chevron-right"
                    label="Next page"
                    size="sm"
                    disabled={pager.page >= pager.pages}
                    onClick={() => {
                      pager.onPage(pager.page + 1);
                    }}
                  />
                </Stack>
              ) : null}
            </Stack>
          }
          toolbarEnd={controls}
        />
      </Stack>
    </Panel>
  );
}
