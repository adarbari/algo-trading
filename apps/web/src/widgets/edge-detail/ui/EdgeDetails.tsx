/**
 * Details of an edge, behind one Disclosure: every test of the verdict with its value and
 * threshold, the backtests (the official result, EXPLORATORY ones, the variants tried and what
 * a run could not read), the Sharpe, deflated Sharpe and overfitting figures, and the user's own
 * out-of-sample split. Every figure and sentence is served.
 */
import {
  DataTable,
  Disclosure,
  Heading,
  KeyValue,
  Mono,
  Stack,
  StatusBadge,
  Text,
  type DataTableGroupBy,
  type KeyValueItem,
} from '@algotrade/ui';

import { verdictLabel, type Edge, type VerdictCriterion } from '@/entities/edge';
import { termHelp } from '@/features/guide-help';

import { criterionColumns } from '../model/columns';

const BY_LEVEL: DataTableGroupBy<VerdictCriterion> = {
  getGroup: (c) => c.level,
  order: ['promising', 'works'],
  label: (group) => verdictLabel(group),
};

const NUMBER = { kind: 'number', digits: 2 } as const;

function Labelled({ text, help }: { text: string; help: string }) {
  return (
    <Stack direction="row" gap={1} align="center">
      <Text size="sm">{text}</Text>
      {termHelp(help)}
    </Stack>
  );
}

function figures(edge: Edge): KeyValueItem[] {
  const v = edge.verdict;
  return [
    { id: 'lift', label: 'Lift (ratio)', value: v.lift, format: NUMBER },
    {
      id: 'sharpe',
      label: <Labelled text="Sharpe ratio" help="sharpe_ratio" />,
      value: v.sharpe,
      format: NUMBER,
    },
    {
      id: 'dsr',
      label: <Labelled text="Deflated Sharpe" help="deflated_sharpe" />,
      value: v.deflatedSharpe,
      format: NUMBER,
    },
    {
      id: 'pbo',
      label: <Labelled text="Overfitting probability" help="overfitting_probability" />,
      value: v.pbo,
      format: NUMBER,
    },
  ];
}

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

export interface EdgeDetailsProps {
  edge: Edge;
}

export function EdgeDetails({ edge }: EdgeDetailsProps) {
  return (
    <Disclosure label="Details" count={String(edge.verdict.criteria.length)}>
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
        <KeyValue label="Figures behind the verdict" items={figures(edge)} />
      </Stack>
    </Disclosure>
  );
}
