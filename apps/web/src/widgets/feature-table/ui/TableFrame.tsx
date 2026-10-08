/**
 * The frame every table of the widget shares: a panel (title, actions, states), the session
 * notes (a stale session, nightly tables missing for it, a universe snapshot from after it; for a
 * screener's run, the run's own coverage: a PARTIAL run and what it ran without),
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

import { UnavailableNote, type ServedUnavailable } from '@/entities/availability';
import { isStale } from '@/entities/explore';
import type { ColumnPlan, TableRow } from '@/entities/feature';
import { helped } from '@/features/guide-help';

/** A screener run's own coverage, as its run record says (not the session as read now). */
export interface RunNotes {
  session: string;
  partial: boolean;
  /** What the tables that had no rows when it ran leave out (ADR 0056). */
  unavailable: readonly ServedUnavailable[];
}

export interface SessionNotes {
  session: string;
  /** What the nightly tables missing for the session leave out, by kind (ADR 0056). */
  unavailable: readonly ServedUnavailable[];
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
  return (
    <>
      {isStale(notes.session) ? (
        <Banner asOf={notes.session}>
          The latest stored session is old: a nightly run may have been missed.
        </Banner>
      ) : null}
      {notes.preSnapshot ? (
        <Banner tone="warning" title="Partial data">
          The universe snapshot is from after this session.
        </Banner>
      ) : null}
      <UnavailableNote gaps={notes.unavailable} />
      {notes.run?.partial ? (
        <Banner tone="warning" title="Partial run">
          {`The run for ${notes.run.session} is PARTIAL; Run now re-runs it.`}
        </Banner>
      ) : null}
      {notes.run ? <UnavailableNote gaps={notes.run.unavailable} /> : null}
    </>
  );
}

function shows(notes: SessionNotes | null | undefined): notes is SessionNotes {
  return (
    !!notes &&
    (isStale(notes.session) ||
      notes.unavailable.length > 0 ||
      notes.preSnapshot ||
      (!!notes.run && (notes.run.partial || notes.run.unavailable.length > 0)))
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
