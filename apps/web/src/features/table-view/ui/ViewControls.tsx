/**
 * A table's view controls, for its toolbar: which of the user's views is in use (the default
 * one, or a named one), "Save view as…" (a dialog naming the current choice) and "Delete view"
 * for a named one. The state is `useTableView`'s.
 */
import { Button, Select, Stack } from '@algotrade/ui';
import { useState } from 'react';

import { errorDetail } from '@/shared/api';

import type { TableViewState } from '../model/table-view';

import { SaveViewDialog } from './SaveViewDialog';

export interface ViewControlsProps {
  view: TableViewState;
}

export function ViewControls({ view }: ViewControlsProps) {
  const [savingAs, setSavingAs] = useState(false);
  return (
    <Stack direction="row" gap={2} align="center">
      <SaveViewDialog
        key={String(savingAs)}
        open={savingAs}
        onOpenChange={setSavingAs}
        taken={view.names}
        saving={view.saving}
        error={view.error ? errorDetail(view.error) : undefined}
        onSave={(name) => {
          view.saveAs(name, () => {
            setSavingAs(false);
          });
        }}
      />
      <Select
        aria-label="View"
        size="sm"
        width="auto"
        value={view.name ?? ''}
        options={[
          { value: '', label: 'Default view' },
          ...view.names.map((n) => ({ value: n, label: n })),
        ]}
        onValueChange={(value) => {
          view.select(value === '' ? null : value);
        }}
      />
      <Button
        size="sm"
        variant="ghost"
        onClick={() => {
          setSavingAs(true);
        }}
      >
        Save view as…
      </Button>
      {view.name !== null ? (
        <Button size="sm" variant="ghost" loading={view.removing} onClick={view.remove}>
          Delete view
        </Button>
      ) : null}
    </Stack>
  );
}
