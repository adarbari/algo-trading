/**
 * The session notice of every page (ADR 0062): pages show the last complete session, and this
 * banner under the top bar says which one and that a newer session is still processing, or
 * failed and is being retried (the public kind only). It stays until the newer session
 * completes, is not snoozable, and renders nothing when the page shows the newest session. The
 * term it opens is the Guide's `last_complete_session`.
 */
import { Banner, formatValue } from '@algotrade/ui';

import { useSessionNotice } from '@/entities/system-status';
import { GuideHelp } from '@/features/guide-help';

export interface SessionNoticeProps {
  /** The viewer may read the nightly run (an admin): the same query as the strip's. */
  admin: boolean;
}

const day = (iso: string) => formatValue(iso, { kind: 'date', style: 'short' }).text;

export function SessionNotice({ admin }: SessionNoticeProps) {
  const notice = useSessionNotice(admin);
  if (notice === null) return null;
  const failing = notice.newer.state === 'FAILED_RETRYING';
  return (
    <Banner
      tone="warning"
      title={`Showing ${day(notice.served)} close`}
      actions={<GuideHelp entry={{ kind: 'term', id: 'last_complete_session' }} />}
    >
      {day(notice.newer.date)} data {failing ? 'failed and is being retried' : 'still processing'}
    </Banner>
  );
}
