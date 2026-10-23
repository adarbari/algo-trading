/**
 * What the status strip shows besides the open issues, in one lazy chunk (the entry chunk is at
 * its budget): the session notice (ADR 0062) when a newer session is incomplete, and the
 * data-status pill with its popover (a right-aligned row, always there once the status read
 * has arrived). Both read the strip's one request.
 */
import { Stack } from '@algotrade/ui';

import type { SessionNotice } from '@/entities/system-status';

import { DataStatusPill } from './DataStatusPill';
import SessionNoticeBanner from './SessionNoticeBanner';

export interface StatusExtrasProps {
  notice: SessionNotice | null;
  /** The viewer may read causes (an admin). */
  admin: boolean;
}

export function StatusExtras({ notice, admin }: StatusExtrasProps) {
  return (
    <>
      {notice !== null && <SessionNoticeBanner notice={notice} />}
      <Stack direction="row" justify="end">
        <DataStatusPill admin={admin} />
      </Stack>
    </>
  );
}

export default StatusExtras;
