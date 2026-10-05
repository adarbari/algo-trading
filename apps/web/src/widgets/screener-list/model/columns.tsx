/**
 * The screeners list's columns. Site presets: name, kind (rules or Python), universe,
 * state and Open / Copy. Your screeners: name, state (DRAFT or vN finalized, a working copy
 * beside it), the preset it copies, universe, Results and Edit.
 */
import { Button, Stack, StatusBadge, type DataTableColumn } from '@algotrade/ui';

import type { ScreenerListItem, ScreenerSummary } from '@/entities/screen';

export interface ScreenerActions {
  /** Open a screener's results. */
  onOpen: (id: string) => void;
  /** Open a screener in the Builder. */
  onEdit: (id: string) => void;
  onCopy: (preset: string) => void;
}

/** One of your screens: the API's listing joined with what its config resolves to. */
export interface MyScreener extends ScreenerListItem {
  selection: string | null;
  error: string | null;
}

const isRules = (screener: ScreenerSummary): boolean => screener.impl === 'rules';

const NAME: DataTableColumn<ScreenerSummary> = {
  id: 'name',
  header: 'Screener',
  value: (s) => s.config_id,
  mono: true,
  hideable: false,
  grow: true,
};

export function presetColumns(actions: ScreenerActions): DataTableColumn<ScreenerSummary>[] {
  return [
    NAME,
    {
      id: 'kind',
      header: 'Kind',
      description:
        'Rule screens are built here; Python screeners are code (changed by pull request)',
      value: (s) => (isRules(s) ? 'Rules' : 'Python'),
      tone: 'secondary',
    },
    {
      id: 'universe',
      header: 'Universe',
      value: (s) => s.selection,
      mono: true,
      tone: 'secondary',
    },
    {
      id: 'actions',
      header: 'Actions',
      value: () => null,
      sortable: false,
      hideable: false,
      width: '2xl', // Open + Copy to my screeners: narrower clips the buttons
      cell: ({ row }) =>
        isRules(row) ? (
          <Stack direction="row" gap={2} justify="end">
            <Button
              size="sm"
              onClick={() => {
                actions.onOpen(row.config_id);
              }}
            >
              Open
            </Button>
            <Button
              size="sm"
              variant="primary"
              onClick={() => {
                actions.onCopy(row.config_id);
              }}
            >
              Copy to my screeners
            </Button>
          </Stack>
        ) : null,
    },
  ];
}

const stateOf = (s: MyScreener): string => {
  if (s.status === 'DRAFT') return 'DRAFT';
  return `v${String(s.latest ?? 1)}${s.has_draft ? ' + draft' : ''}`;
};

export function myColumns(actions: ScreenerActions): DataTableColumn<MyScreener>[] {
  return [
    {
      id: 'name',
      header: 'Screener',
      value: (s) => s.screener_id,
      mono: true,
      hideable: false,
      grow: true,
    },
    {
      id: 'state',
      header: 'State',
      description: 'DRAFT: not finalized yet; vN: its newest finalized version',
      value: stateOf,
      cell: ({ row }) =>
        row.error ? (
          <StatusBadge tone="negative" title={row.error}>
            Does not resolve
          </StatusBadge>
        ) : (
          <StatusBadge tone={row.status === 'DRAFT' ? 'accent' : 'positive'}>
            {stateOf(row)}
          </StatusBadge>
        ),
    },
    {
      id: 'preset',
      header: 'Copy of',
      value: (s) => s.preset_id,
      mono: true,
      tone: 'secondary',
    },
    {
      id: 'universe',
      header: 'Universe',
      value: (s) => s.selection,
      mono: true,
      tone: 'secondary',
    },
    {
      id: 'actions',
      header: 'Actions',
      value: () => null,
      sortable: false,
      hideable: false,
      width: 'xl',
      cell: ({ row }) => (
        <Stack direction="row" gap={2} justify="end">
          <Button
            size="sm"
            onClick={() => {
              actions.onOpen(row.screener_id);
            }}
          >
            Results
          </Button>
          <Button
            size="sm"
            onClick={() => {
              actions.onEdit(row.screener_id);
            }}
          >
            Edit
          </Button>
        </Stack>
      ),
    },
  ];
}
