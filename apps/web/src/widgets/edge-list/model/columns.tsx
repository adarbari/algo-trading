/**
 * The edges list's columns: the edge (its screens beneath), its verdict (with its Guide button),
 * the out-of-sample result (the server's sentence), the trades behind it and where the user stands
 * (their own state, else the site's status). The
 * rows are edge documents, not instruments; every figure and sentence is served.
 */
import { StatusBadge, Stack, Text, type DataTableColumn } from '@algotrade/ui';

import {
  stateOrStatus,
  stateTone,
  statusTone,
  verdictLabel,
  verdictTone,
  type Edge,
} from '@/entities/edge';
import { GuideHelp } from '@/features/guide-help';

const screensOf = (e: Edge): string =>
  e.screeners.length === 0
    ? 'no screen yet'
    : `${e.screeners.length === 1 ? 'screen' : 'screens'}: ${e.screeners.join(', ')}`;

export function edgeColumns(): DataTableColumn<Edge>[] {
  return [
    {
      id: 'name',
      header: 'Edge',
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
            {`${row.mine ? 'mine' : 'site edge'} · ${screensOf(row)}`}
          </Text>
        </Stack>
      ),
    },
    {
      id: 'verdict',
      header: 'Verdict',
      headerAction: <GuideHelp entry={{ kind: 'term', id: 'verdict' }} />,
      value: (e) => verdictLabel(e.verdict.verdict),
      essential: true,
      cell: ({ row }) => (
        <StatusBadge tone={verdictTone(row.verdict.verdict)}>
          {verdictLabel(row.verdict.verdict)}
        </StatusBadge>
      ),
    },
    {
      id: 'result',
      header: 'Out-of-sample result',
      headerAction: <GuideHelp entry={{ kind: 'term', id: 'out_of_sample' }} />,
      value: (e) => e.verdict.result,
      grow: true,
      tone: 'secondary',
    },
    {
      id: 'trades',
      header: 'Trades',
      headerAction: <GuideHelp entry={{ kind: 'term', id: 'trades' }} />,
      value: (e) => e.verdict.trades ?? null,
      format: { kind: 'number' },
      align: 'end',
    },
    {
      id: 'status',
      header: 'Status',
      headerAction: <GuideHelp entry={{ kind: 'term', id: 'edge_state' }} />,
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
