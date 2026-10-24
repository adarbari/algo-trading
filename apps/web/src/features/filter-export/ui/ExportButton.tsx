/**
 * The Export button of a filter bar (ADR 0082 decision 6): saves the rows the filters in force
 * leave as a CSV file, with its Guide help beside it (the caller's `help`: what Export writes and
 * what the licence notice means), and says when the file could not be saved. States: idle, saving,
 * failed.
 */
import { Button, Stack, Text } from '@algotrade/ui';
import type { ReactNode } from 'react';

import { useSurfaceExport } from '../api/use-surface-export';

export interface ExportButtonProps {
  /** The surface name (`ideas`): the file route's key. */
  surface: string;
  /** The `f` string of the filters in force (empty: none). */
  f: string;
  /** The session the page shows (`2026-10-01`): the file is for that session, not the latest. */
  session?: string | null | undefined;
  /** The help button of the Export Guide entry (the caller's `termHelp('export')`). */
  help?: ReactNode;
}

export function ExportButton({ surface, f, session, help }: ExportButtonProps) {
  const file = useSurfaceExport(surface);
  return (
    <Stack direction="row" gap={1} align="center">
      <Button
        size="sm"
        variant="secondary"
        loading={file.isPending}
        onClick={() => {
          file.mutate({ f, session });
        }}
      >
        Export
      </Button>
      {help}
      {file.isError && <Text tone="negative">The file could not be saved.</Text>}
    </Stack>
  );
}
