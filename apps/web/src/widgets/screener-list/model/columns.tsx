/** The screeners list's columns: name, kind (rules or Python), universe, schedule, state, and the row's actions. */
import { Button, Stack, StatusBadge, type DataTableColumn } from '@algotrade/ui';

import type { ScreenerSummary } from '@/entities/screen';

export interface ScreenerActions {
  onOpen: (id: string) => void;
  onCopy: (preset: string) => void;
}

const isRules = (screener: ScreenerSummary): boolean => screener.impl === 'rules';

export function screenerColumns(actions: ScreenerActions): DataTableColumn<ScreenerSummary>[] {
  return [
    {
      id: 'name',
      header: 'Screener',
      value: (s) => s.config_id,
      mono: true,
      hideable: false,
      grow: true,
    },
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
      id: 'schedule',
      header: 'Schedule',
      value: (s) => (s.schedule === 'nightly' ? 'Nightly' : 'Off'),
      tone: 'secondary',
    },
    {
      id: 'state',
      header: 'State',
      value: (s) => s.error,
      sortable: false,
      cell: ({ row }) =>
        row.error ? (
          <StatusBadge tone="negative" title={row.error}>
            Does not resolve
          </StatusBadge>
        ) : null,
    },
    {
      id: 'actions',
      header: 'Actions',
      value: () => null,
      sortable: false,
      hideable: false,
      width: 'lg',
      cell: ({ row }) =>
        isRules(row) ? (
          <Stack direction="row" gap={2} justify="end">
            <Button
              size="sm"
              onClick={() => {
                actions.onOpen(row.config_id);
              }}
            >
              {row.scope === 'site' ? 'View' : 'Edit'}
            </Button>
            {row.scope === 'site' && (
              <Button
                size="sm"
                variant="primary"
                onClick={() => {
                  actions.onCopy(row.config_id);
                }}
              >
                Copy to my screeners
              </Button>
            )}
          </Stack>
        ) : null,
    },
  ];
}
