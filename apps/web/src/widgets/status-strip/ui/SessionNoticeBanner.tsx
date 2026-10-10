/**
 * The banner of the session notice (ADR 0062): which close the pages show and that a newer
 * session is still processing, or failed and is being retried (the public kind only), with the
 * button that opens the Guide's `last_complete_session` term. Lazy: loaded only when a newer
 * incomplete session exists, so the entry chunk does not carry it.
 */
import { Banner, formatValue } from '@algotrade/ui';

import type { SessionNotice } from '@/entities/system-status';
import { GuideHelp } from '@/features/guide-help';

const day = (iso: string) => formatValue(iso, { kind: 'date', style: 'short' }).text;

export function SessionNoticeBanner({ notice }: { notice: SessionNotice }) {
  if (notice.newer === null) return null;
  const failing = notice.newer.state === 'FAILED_RETRYING';
  return (
    <Banner
      tone="warning"
      title={`Showing ${day(notice.date)} close`}
      actions={<GuideHelp entry={{ kind: 'term', id: 'last_complete_session' }} />}
    >
      {day(notice.newer.date)} data {failing ? 'failed and is being retried' : 'still processing'}
    </Banner>
  );
}

export default SessionNoticeBanner;
