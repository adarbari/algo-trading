/**
 * The setups library's columns: the setup (its idea beneath), its verdict (with its Guide button),
 * the out-of-sample result (the server's sentence), the trades behind it and where the user stands
 * (their own state, else the site's status) and the live state (the badge of a recorded edge). The
 * rows are edge documents, not instruments; every figure and sentence is served.
 */
import { StatusBadge, Stack, Text, type DataTableColumn } from '@algotrade/ui';

import {
  recordLabel,
  recordTone,
  stateOrStatus,
  stateTone,
  statusTone,
  verdictLabel,
  verdictTone,
  type EdgeRow,
  type LiveState,
} from '@/entities/edge';
import { termHelp } from '@/features/guide-help';

/** `live`: each recorded edge's live state by edge id (an edge without one shows nothing). */
export function edgeColumns(live: ReadonlyMap<string, LiveState>): DataTableColumn<EdgeRow>[] {
  return [
    {
      id: 'name',
      header: 'Setup',
      value: (e) => e.name,
      hideable: false,
      grow: true,
      essential: true,
      cell: ({ row }) => (
        <Stack gap={0}>
          <Text size="sm" weight="medium">
            {row.name}
          </Text>
          <Text size="xs" tone="muted">
            {row.thesis}
          </Text>
        </Stack>
      ),
    },
    {
      id: 'verdict',
      header: 'Verdict',
      headerAction: termHelp('verdict'),
      value: (e) => verdictLabel(e.summary.verdict),
      essential: true,
      cell: ({ row }) => (
        <StatusBadge tone={verdictTone(row.summary.verdict)}>
          {verdictLabel(row.summary.verdict)}
        </StatusBadge>
      ),
    },
    {
      id: 'result',
      header: 'Backtest · out of sample (hypothetical)',
      headerAction: termHelp('out_of_sample'),
      value: (e) => e.summary.result,
      grow: true,
      tone: 'secondary',
    },
    {
      id: 'trades',
      header: 'Trades',
      headerAction: termHelp('trades'),
      value: (e) => e.summary.trades ?? null,
      format: { kind: 'number' },
      align: 'end',
    },
    {
      id: 'live',
      header: 'Live',
      headerAction: termHelp('live_state'),
      value: (e) => {
        const state = live.get(e.id)?.state;
        return state ? recordLabel(state) : '';
      },
      cell: ({ row }) => {
        const state = live.get(row.id)?.state;
        return state ? (
          <StatusBadge tone={recordTone(state)}>{recordLabel(state)}</StatusBadge>
        ) : null;
      },
    },
    {
      id: 'status',
      header: 'Status',
      headerAction: termHelp('edge_state'),
      value: stateOrStatus,
      tone: 'secondary',
      cell: ({ row }) => (
        <StatusBadge
          tone={row.state === 'researching' ? statusTone(row.status) : stateTone(row.state)}
        >
          {stateOrStatus(row)}
        </StatusBadge>
      ),
    },
  ];
}
