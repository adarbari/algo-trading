/** "Finalize vN": saves any unsaved edits as the draft, then freezes the draft as the next version. */
import { Button } from '@algotrade/ui';

import { useFinalise } from '../api/hooks';

export interface FinaliseButtonProps {
  screenerId: string;
  /** The version finalising creates. */
  version: number;
  /** Saves the unsaved edits first (a draft finalises as saved). */
  prepare: () => Promise<void>;
  disabled?: boolean;
  /** The Describe-it session this screen came from (ADR 0066), sent with the finalise. */
  draftSessionId?: string | null;
  /** The version was written: the session is over. */
  onFinalised?: () => void;
}

export function FinaliseButton({
  screenerId,
  version,
  prepare,
  disabled = false,
  draftSessionId = null,
  onFinalised,
}: FinaliseButtonProps) {
  const finalise = useFinalise(screenerId);
  return (
    <Button
      variant="primary"
      disabled={disabled}
      loading={finalise.isPending}
      onClick={() => {
        void prepare()
          .then(() => finalise.mutateAsync(draftSessionId))
          .then(() => onFinalised?.())
          .catch(() => undefined);
      }}
    >
      {`Finalize v${String(version)}`}
    </Button>
  );
}
