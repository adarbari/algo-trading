/**
 * "Views": the user's saved views of a surface in a popover on the toolbar (ADR 0082, #912): each
 * view is listed with the filters it holds (the same words as the chips, from the definitions),
 * clicking one applies it (filters the surface no longer defines are dropped and named), the x
 * deletes it, and under the list the current filters are saved under a name. The state is
 * `useTableView`'s, so a page that keeps columns and sort in a view shares it with this menu.
 */
import { Button, Field, IconButton, Input, NoticeLine, Popover, Stack, Text } from '@algotrade/ui';
import { useState } from 'react';

import type { FilterDefinition } from '@/entities/filter';
import { useSavedView, type TableViewState } from '@/entities/saved-view';
import { errorDetail } from '@/shared/api';

import type { FilterStateApi } from '../api/use-filter-state';
import { decodeFilters } from '../model/codec';
import { filtersSummary, type LabelOf } from '../model/surface';

const MAX_NAME = 40;

export interface ViewsMenuProps {
  view: TableViewState;
  state: FilterStateApi;
  definitions: readonly FilterDefinition[];
  labelOf: LabelOf | undefined;
}

function ViewRow({
  view,
  name,
  definitions,
  labelOf,
  onDone,
}: {
  view: TableViewState;
  name: string;
  definitions: readonly FilterDefinition[];
  labelOf: LabelOf | undefined;
  onDone: () => void;
}) {
  const saved = useSavedView(view.scope, name);
  const held = filtersSummary(decodeFilters(saved.data?.filters), definitions, labelOf);
  return (
    <Stack direction="row" gap={1} align="center" justify="between">
      <Button
        variant="ghost"
        size="sm"
        aria-pressed={view.name === name}
        onClick={() => {
          view.select(name);
          onDone();
        }}
      >
        <Stack gap={0} align="start">
          <Text weight="medium">{name}</Text>
          {held !== '' && (
            <Text size="sm" tone="muted">
              {held}
            </Text>
          )}
        </Stack>
      </Button>
      <IconButton
        icon="trash"
        size="sm"
        label={`Delete view ${name}`}
        onClick={() => {
          view.remove(name);
        }}
      />
    </Stack>
  );
}

export function ViewsMenu({ view, state, definitions, labelOf }: ViewsMenuProps) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const trimmed = name.trim();
  const current = filtersSummary(state.filters, definitions, labelOf);
  const problem =
    trimmed.length > MAX_NAME
      ? `${String(MAX_NAME)} at most`
      : view.error
        ? errorDetail(view.error)
        : undefined;
  return (
    <Stack gap={1}>
      <Popover
        label="Views"
        open={open}
        onOpenChange={setOpen}
        trapFocus
        trigger={(props) => (
          <Button {...props} size="sm" iconEnd="chevron-down" selected={view.name !== null}>
            {view.names.length > 0 ? `Views · ${String(view.names.length)}` : 'Views'}
          </Button>
        )}
      >
        <Stack gap={3}>
          {view.names.length > 0 && (
            <Stack gap={1}>
              <Button
                variant="ghost"
                size="sm"
                aria-pressed={view.name === null}
                onClick={() => {
                  view.select(null);
                  setOpen(false);
                }}
              >
                Default view
              </Button>
              {view.names.map((n) => (
                <ViewRow
                  key={n}
                  view={view}
                  name={n}
                  definitions={definitions}
                  labelOf={labelOf}
                  onDone={() => {
                    setOpen(false);
                  }}
                />
              ))}
            </Stack>
          )}
          <Field label="Name of the view" {...(problem ? { error: problem } : {})}>
            <Input value={name} onValueChange={setName} autoComplete="off" spellCheck={false} />
          </Field>
          {current !== '' && (
            <Text size="sm" tone="muted">
              {current}
            </Text>
          )}
          <Button
            variant="primary"
            size="sm"
            disabled={trimmed === '' || trimmed.length > MAX_NAME}
            loading={view.saving}
            onClick={() => {
              view.saveAs(trimmed, () => {
                setName('');
                setOpen(false);
              });
            }}
          >
            {view.names.includes(trimmed) ? 'Replace view' : 'Save view'}
          </Button>
        </Stack>
      </Popover>
      {view.droppedFilters.length > 0 && (
        <NoticeLine
          label={`Not applied · ${String(view.droppedFilters.length)}`}
          summary={view.droppedFilters.join(', ')}
        />
      )}
    </Stack>
  );
}
