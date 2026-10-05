/** "Delete screener?": confirms, then deletes (archives) the user's screener. */
import { Button, Dialog, Text } from '@algotrade/ui';

import { useDeleteScreener } from '../api/hooks';

export interface DeleteScreenerDialogProps {
  screenerId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The screener is gone: leave its pages. */
  onDeleted: () => void;
}

export function DeleteScreenerDialog({
  screenerId,
  open,
  onOpenChange,
  onDeleted,
}: DeleteScreenerDialogProps) {
  const remove = useDeleteScreener(screenerId);
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      size="sm"
      title={`Delete ${screenerId}?`}
      description="Its draft and every finalized version go, and it stops running nightly."
      footer={
        <>
          <Button
            variant="ghost"
            onClick={() => {
              onOpenChange(false);
            }}
          >
            Cancel
          </Button>
          <Button
            variant="primary"
            loading={remove.isPending}
            onClick={() => {
              remove.mutate(undefined, { onSuccess: onDeleted });
            }}
          >
            Delete
          </Button>
        </>
      }
    >
      <Text size="sm" tone="muted">
        Past results stay readable in the run history. The files are archived in your config folder,
        so it can be restored by hand.
      </Text>
    </Dialog>
  );
}
