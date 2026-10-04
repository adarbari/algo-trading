/**
 * The preview table's columns: symbol, decision, score, one column per value the screen stores
 * with each row (`[columns]`), the flags and the reasons for the decision.
 */
import { type DataTableColumn } from '@algotrade/ui';

import { ScreenDecisionBadge, type PreviewRow } from '@/entities/screen';

const cell = (value: unknown): unknown =>
  typeof value === 'boolean' ? (value ? 'Yes' : 'No') : value;

export function previewColumns(extra: readonly string[]): DataTableColumn<PreviewRow>[] {
  return [
    {
      id: 'rank',
      header: '#',
      description: 'Rank by score, then the tie-break column',
      value: (row) => row.rank,
      format: { kind: 'number' },
      width: 'xs',
      hideable: false,
    },
    {
      id: 'symbol',
      header: 'Symbol',
      value: (row) => row.symbol ?? row.instrument_id,
      mono: true,
      hideable: false,
    },
    {
      id: 'decision',
      header: 'Decision',
      value: (row) => row.decision,
      cell: ({ row }) => <ScreenDecisionBadge decision={row.decision} />,
    },
    {
      id: 'score',
      header: 'Score',
      description: 'For sorting only: 100 minus the penalties of each miss',
      value: (row) => row.score,
      format: { kind: 'number', digits: 0 },
    },
    ...extra.map((name): DataTableColumn<PreviewRow> => ({
      id: `col:${name}`,
      header: name.replace(/_/g, ' '),
      description: `The screen's column ${name}`,
      value: (row) => cell(row.columns[name]),
      format: { kind: 'number', digits: 2 },
    })),
    {
      id: 'flags',
      header: 'Flags',
      value: (row) => row.flags.join(', ') || null,
      tone: 'secondary',
    },
    {
      id: 'reasons',
      header: 'Why',
      description: 'The misses behind a decision other than QUALIFIED',
      value: (row) => row.reasons.join('; ') || null,
      grow: true,
      tone: 'secondary',
    },
  ];
}
