/** "Delete": opens the confirmation for deleting the user's screener. */
import { Button } from '@algotrade/ui';
import { useState } from 'react';

import { DeleteScreenerDialog } from './DeleteScreenerDialog';

export interface DeleteScreenerButtonProps {
  screenerId: string;
  /** The screener is gone: leave its pages. */
  onDeleted: () => void;
  disabled?: boolean;
}

export function DeleteScreenerButton({
  screenerId,
  onDeleted,
  disabled = false,
}: DeleteScreenerButtonProps) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button
        variant="ghost"
        disabled={disabled}
        onClick={() => {
          setOpen(true);
        }}
      >
        Delete
      </Button>
      <DeleteScreenerDialog
        screenerId={screenerId}
        open={open}
        onOpenChange={setOpen}
        onDeleted={() => {
          setOpen(false);
          onDeleted();
        }}
      />
    </>
  );
}
