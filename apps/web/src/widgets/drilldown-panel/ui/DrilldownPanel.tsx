/**
 * The drill-down of one completeness cell: how its items ended (a StackedBar by status), the
 * fetch-priority tiers for option chains, the issues grouped by reason with examples and a
 * hint, and actions: the run record (a Drawer), the items as CSV, and re-run (disabled until
 * the jobs API exists).
 */
import {
  BarList,
  Button,
  Disclosure,
  EmptyState,
  ErrorState,
  formatValue,
  Mono,
  Panel,
  Skeleton,
  Stack,
  StackedBar,
  StatusBadge,
  Text,
  Tooltip,
} from '@algotrade/ui';
import { useState } from 'react';

import { DownloadItemsButton } from '@/features/download-items';
import {
  datasetLabel,
  isChains,
  useCellDetail,
  useFocusCell,
  type CellRef,
} from '@/entities/ingestion';
import {
  RunRecordDrawer,
  RunStatusBadge,
  statusHint,
  statusTone,
  type FailureGroup,
} from '@/entities/run';

import { examplesText, fetchTiers, primaryRun, statusSegments } from '../model/drilldown';

export interface DrilldownPanelProps {
  /** The selected cell; none drills into the latest session's worst cell. */
  selected?: CellRef | null;
}

const weekday = (day: string) => formatValue(day, { kind: 'date', style: 'weekday' }).text;
const count = (n: number | null) => formatValue(n, { kind: 'number' }).text;

function Issue({ group, open }: { group: FailureGroup; open: boolean }) {
  const tone = statusTone(group.reason);
  const hint = statusHint(group.reason);
  return (
    <Disclosure
      label={group.reason}
      count={count(group.count)}
      countTone={tone === 'neutral' || tone === 'accent' || tone === 'info' ? 'default' : tone}
      defaultOpen={open}
    >
      <Stack gap={1}>
        <Mono size="xs" tone="secondary">
          {examplesText(group.examples, group.count)}
        </Mono>
        {hint && (
          <Text size="sm" tone="muted">
            {hint}
          </Text>
        )}
      </Stack>
    </Disclosure>
  );
}

export function DrilldownPanel({ selected }: DrilldownPanelProps) {
  const cell = useFocusCell(selected);
  const detail = useCellDetail(cell);
  const [drawer, setDrawer] = useState(false);
  const title = cell ? `${datasetLabel(cell.dataset)} · ${weekday(cell.session)}` : 'Drill-down';
  const data = detail.data;
  const run = data ? primaryRun(data) : undefined;
  const tiers = fetchTiers(run);
  const description = data
    ? data.cell.expected === null
      ? `${count(data.cell.present)} rows · ${data.cell.basis}`
      : `${count(data.cell.present)} of ${count(data.cell.expected)} expected · ${data.cell.basis}`
    : undefined;

  return (
    <Panel
      title={title}
      description={description}
      actions={data && <RunStatusBadge status={data.cell.status} />}
    >
      {!cell ? (
        <EmptyState
          compact
          title="No cell selected"
          description="Select a cell of the grid to drill in."
        />
      ) : detail.isPending ? (
        <Skeleton lines={6} label="Loading the drill-down…" />
      ) : detail.isError ? (
        <ErrorState
          compact
          title="The drill-down could not load."
          detail={detail.error.message}
          onRetry={() => void detail.refetch()}
          retrying={detail.isFetching}
        />
      ) : !data ? (
        <EmptyState
          compact
          title="Not a dataset of the grid"
          description={`${cell.dataset} is not tracked for completeness.`}
        />
      ) : (
        <Stack gap={4}>
          <StackedBar
            label={
              run
                ? `Items of ${run.job}, ${weekday(cell.session)}`
                : `Rows, ${weekday(cell.session)}`
            }
            segments={statusSegments(data, run)}
            {...(run ? {} : data.cell.expected ? { total: data.cell.expected } : {})}
            emptyMessage="No rows or items recorded for this cell."
          />
          {isChains(cell.dataset) && (
            <Stack gap={1}>
              <Text size="sm" tone="muted">
                Fetch order (underlyings per priority tier)
              </Text>
              {tiers.length > 0 ? (
                <BarList label="Underlyings by fetch priority tier" items={tiers} />
              ) : (
                <Text size="sm" tone="muted">
                  This run did not record its fetch tiers.
                </Text>
              )}
            </Stack>
          )}
          <Stack gap={2}>
            <Text size="sm" tone="muted">
              Issues, grouped
            </Text>
            {data.groups.length === 0 ? (
              <StatusBadge tone="positive" icon="check">
                No issues recorded
              </StatusBadge>
            ) : (
              data.groups.map((g, i) => <Issue key={g.reason} group={g} open={i === 0} />)
            )}
          </Stack>
          <Stack direction="row" gap={2} wrap>
            <Button
              disabled={!run}
              onClick={() => {
                setDrawer(true);
              }}
            >
              Open run record
            </Button>
            <DownloadItemsButton runId={run?.runId ?? null} />
            <Tooltip content="Coming with the jobs API: the API is read-only for now.">
              {(props) => (
                <Button {...props} variant="primary" icon="refresh" disabled>
                  {`Re-run ${datasetLabel(cell.dataset).toLowerCase()} for ${weekday(cell.session)}`}
                </Button>
              )}
            </Tooltip>
          </Stack>
          <RunRecordDrawer runId={run?.runId ?? null} open={drawer} onOpenChange={setDrawer} />
        </Stack>
      )}
    </Panel>
  );
}
