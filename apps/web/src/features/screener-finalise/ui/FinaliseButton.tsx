/** "Finalize vN": saves any unsaved edits as the draft, then freezes the draft as the next version. */
import { Button } from '@algotrade/ui';

import { errorDetail } from '@/shared/api';

import { useFinalise, type FinaliseInput } from '../api/hooks';

type DraftChoice = NonNullable<FinaliseInput['choices']>[number];

export interface FinaliseButtonProps {
  screenerId: string;
  /** The version finalising creates. */
  version: number;
  /** Saves the unsaved edits first (a draft finalises as saved). */
  prepare: () => Promise<void>;
  disabled?: boolean;
  /** The Describe-it session this screen came from (ADR 0066), sent with the finalise. */
  draftSessionId?: string | null;
  /** What the trader decided on the draft's options, sent with the finalise. */
  choices?: readonly DraftChoice[];
  /** The version was written: the session is over. */
  onFinalised?: () => void;
  /** Checked first: false means nothing is saved or sent (the caller shows why). */
  validate?: () => boolean;
  /** The server refused the finalise: its message. */
  onRefused?: (message: string) => void;
}

export function FinaliseButton({
  screenerId,
  version,
  prepare,
  disabled = false,
  draftSessionId = null,
  choices = [],
  onFinalised,
  validate,
  onRefused,
}: FinaliseButtonProps) {
  const finalise = useFinalise(screenerId);
  return (
    <Button
      variant="primary"
      disabled={disabled}
      loading={finalise.isPending}
      onClick={() => {
        if (validate && !validate()) return;
        void prepare()
          .then(() => finalise.mutateAsync({ draftSessionId, choices }))
          .then(() => onFinalised?.())
          .catch((error: unknown) => {
            onRefused?.(errorDetail(error));
          });
      }}
    >
      {`Finalize v${String(version)}`}
    </Button>
  );
}
