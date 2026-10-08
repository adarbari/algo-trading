/**
 * The screeners list's columns. Site presets: name, kind (rules or Python), universe,
 * state, Playbook (its Guide page) and Copy. Your screeners: name, state (DRAFT or vN
 * finalized, a working copy beside it), the preset it copies, universe, Edit and Delete. A row
 * click opens the screener (ScreenerList), so no row has an Open button.
 */
import { Button, Stack, StatusBadge, TextLink, type DataTableColumn } from '@algotrade/ui';

import { playbookPath } from '@/entities/guide';
import type { ScreenerListItem, ScreenerSummary } from '@/entities/screen';

export interface ScreenerActions {
  /** Open a screener in the Builder. */
  onEdit: (id: string) => void;
  onCopy: (preset: string) => void;
  /** Ask to delete one of your screeners. */
  onDelete: (id: string) => void;
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
  value: (s) => s.configId,
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
      width: '2xl', // Playbook + Copy to my screeners: narrower clips them
      cell: ({ row }) =>
        isRules(row) ? (
          <Stack direction="row" gap={3} justify="end" align="center">
            <TextLink href={playbookPath(row.configId)} icon="book" size="sm">
              Playbook
            </TextLink>
            <Button
              size="sm"
              variant="primary"
              onClick={() => {
                actions.onCopy(row.configId);
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
  return `v${String(s.latest ?? 1)}${s.hasDraft ? ' + draft' : ''}`;
};

export function myColumns(actions: ScreenerActions): DataTableColumn<MyScreener>[] {
  return [
    {
      id: 'name',
      header: 'Screener',
      value: (s) => s.screenerId,
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
      value: (s) => s.presetId,
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
              actions.onEdit(row.screenerId);
            }}
          >
            Edit
          </Button>
          <Button
            size="sm"
            variant="ghost"
            aria-label={`Delete ${row.screenerId}`}
            onClick={() => {
              actions.onDelete(row.screenerId);
            }}
          >
            Delete
          </Button>
        </Stack>
      ),
    },
  ];
}
