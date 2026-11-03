/**
 * Confirm removing a name from the scope list, with an optional note. A name of the site file
 * stays in the file: the removal is the admin's, recorded beside it, and adding it again
 * restores it. A refusal shows the server's detail.
 */
import { Banner, Button, Dialog, Field, Input, Stack } from '@algotrade/ui';
import { useState } from 'react';

import { errorDetail } from '@/shared/api';

import { useRemoveScopeName } from '../api/hooks';

export interface RemoveScopeNameDialogProps {
  symbol: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function RemoveScopeNameDialog({ symbol, open, onOpenChange }: RemoveScopeNameDialogProps) {
  const [note, setNote] = useState('');
  const remove = useRemoveScopeName();
  const close = () => {
    onOpenChange(false);
  };
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={`Remove ${symbol}`}
      footer={
        <>
          <Button variant="ghost" onClick={close}>
            Cancel
          </Button>
          <Button
            variant="primary"
            loading={remove.isPending}
            onClick={() => {
              remove.mutate(
                { symbol, note },
                {
                  onSuccess: () => {
                    setNote('');
                    close();
                  },
                },
              );
            }}
          >
            Remove
          </Button>
        </>
      }
    >
      <Stack gap={3}>
        <Field label="Note (optional)">
          <Input value={note} onValueChange={setNote} autoComplete="off" maxLength={200} />
        </Field>
        {remove.error && <Banner tone="negative">{errorDetail(remove.error)}</Banner>}
      </Stack>
    </Dialog>
  );
}
