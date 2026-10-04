/** "A newer preset version is available": rebase keeps the user's overrides and re-pins the preset. */
import { Banner, Button } from '@algotrade/ui';

import { useRebase } from '../api/hooks';

export interface RebaseBannerProps {
  screenerId: string;
  preset: string;
  pinned: number;
  current: number;
  /** Unsaved edits would be lost: save the draft first. */
  disabled?: boolean;
}

export function RebaseBanner({
  screenerId,
  preset,
  pinned,
  current,
  disabled = false,
}: RebaseBannerProps) {
  const rebase = useRebase(screenerId);
  return (
    <Banner
      tone="info"
      title="Rebase available"
      actions={
        <Button
          size="sm"
          loading={rebase.isPending}
          disabled={disabled}
          onClick={() => {
            rebase.mutate();
          }}
        >
          {`Rebase on v${String(current)}`}
        </Button>
      }
    >
      {`${preset} has a newer version (v${String(current)}); this screener is pinned to v${String(pinned)}. Rebasing keeps your changes${disabled ? ' (save the draft first)' : ''}.`}
    </Banner>
  );
}
