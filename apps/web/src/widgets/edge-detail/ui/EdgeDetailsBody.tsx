/**
 * The body of an edge's Details, loaded on first open (its own chunk): every test of the verdict
 * with its value and threshold, and the backtests (the official result, EXPLORATORY ones, the
 * variants tried and what a run could not read). Every figure and sentence is served.
 */
import {
  DataTable,
  Heading,
  Mono,
  Stack,
  StatusBadge,
  Text,
  type DataTableGroupBy,
} from '@algotrade/ui';

import { verdictLabel, type Edge, type VerdictCriterion } from '@/entities/edge';
import { termHelp } from '@/features/guide-help';

import { criterionColumns } from '../model/columns';

const BY_LEVEL: DataTableGroupBy<VerdictCriterion> = {
  getGroup: (c) => c.level,
  order: ['promising', 'works'],
  label: (group) => verdictLabel(group),
};

function Backtests({ edge }: { edge: Edge }) {
  if (edge.runs.length === 0) return <Text size="sm">No backtest yet</Text>;
  return (
    <Stack gap={2}>
      {edge.runs.map((run) => (
        <Stack key={run.runId} gap={0}>
          <Stack direction="row" gap={2} align="center" wrap>
            <Mono size="sm">{run.runId}</Mono>
            <Text size="sm" tone="muted">
              {`out-of-sample from ${run.splitFrom ?? 'none'} · to ${run.rangeTo}`}
            </Text>
            {run.runId === edge.canonicalRun?.runId && (
              <>
                <StatusBadge tone="info">Official result</StatusBadge>
                {termHelp('official_result')}
              </>
            )}
            {run.exploratory && (
              <>
                <StatusBadge tone="warning">EXPLORATORY</StatusBadge>
                {termHelp('exploratory')}
              </>
            )}
            {run.trialsCounted != null && (
              <Text size="sm" tone="muted">{`${run.trialsCounted} variants tried`}</Text>
            )}
          </Stack>
          {run.lostInputs.map((gap) => (
            <Text key={gap} size="sm" tone="muted">
              {gap}
            </Text>
          ))}
        </Stack>
      ))}
    </Stack>
  );
}

/** What the Details disclosure shows once opened. */
export function EdgeDetailsBody({ edge }: { edge: Edge }) {
  return (
    <Stack gap={4}>
      <Stack gap={2}>
        <Stack direction="row" gap={1} align="center">
          <Heading level={3}>What the verdict tests</Heading>
          {termHelp('verdict_criteria')}
          {termHelp('baselines')}
        </Stack>
        <DataTable<VerdictCriterion>
          label="Verdict tests"
          columns={criterionColumns}
          rows={edge.verdict.criteria}
          getRowId={(c) => c.id}
          groupBy={BY_LEVEL}
          emptyMessage="No tests yet: the edge has no official result"
          visibleRows={14}
        />
      </Stack>
      <Stack gap={2}>
        <Stack direction="row" gap={1} align="center">
          <Heading level={3}>Backtests</Heading>
          {termHelp('edge_backtests')}
          {termHelp('variants_tried')}
        </Stack>
        <Backtests edge={edge} />
      </Stack>
    </Stack>
  );
}
