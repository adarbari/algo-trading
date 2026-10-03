/**
 * Download a run's items as CSV (key, code, status), built in the browser from the API's item
 * list. Confirms with a toast ("4,204 items saved"); a failure is a negative toast.
 */
import { Button, formatValue, saveTextFile, useToast } from '@algotrade/ui';
import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { itemsCsv, itemsFileName, runItemsQuery } from '@/entities/run';

export interface DownloadItemsButtonProps {
  /** The run whose items are saved; none disables the button. */
  runId: string | null;
}

export function DownloadItemsButton({ runId }: DownloadItemsButtonProps) {
  const client = useQueryClient();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const download = async (id: string) => {
    setBusy(true);
    try {
      const items = await client.query(runItemsQuery(id));
      saveTextFile(itemsFileName(id), itemsCsv(items));
      toast.show({
        tone: 'positive',
        title: `${formatValue(items.length, { kind: 'number' }).text} items saved`,
        description: itemsFileName(id),
      });
    } catch (error) {
      toast.show({
        tone: 'negative',
        title: 'The items could not be downloaded',
        description: error instanceof Error ? error.message : String(error),
      });
    } finally {
      setBusy(false);
    }
  };
  return (
    <Button
      loading={busy}
      disabled={!runId}
      onClick={() => {
        if (runId) void download(runId);
      }}
    >
      Download items (CSV)
    </Button>
  );
}
