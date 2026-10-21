/**
 * The banner of the session notice (ADR 0062): which close the pages show and that a newer
 * session is still processing, failed and is being retried (the public kind only), or complete and
 * being published, with the
 * button that opens the Guide's `last_complete_session` term. Lazy: loaded only when a newer
 * incomplete session exists, so the entry chunk does not carry it.
 */
import { Banner, formatValue } from '@algotrade/ui';

import type { SessionNotice } from '@/entities/system-status';
import { GuideHelp } from '@/features/guide-help';

const day = (iso: string) => formatValue(iso, { kind: 'date', style: 'short' }).text;

const WORDS = {
  IN_PROGRESS: 'still processing',
  FAILED_RETRYING: 'failed and is being retried',
  PUBLISHING: 'is being published',
} as const;

export function SessionNoticeBanner({ notice }: { notice: SessionNotice }) {
  if (notice.newer === null) return null;
  const { state } = notice.newer;
  const term = state === 'PUBLISHING' ? 'publishing_session' : 'last_complete_session';
  return (
    <Banner
      tone="warning"
      title={`Showing ${day(notice.date)} close`}
      actions={<GuideHelp entry={{ kind: 'term', id: term }} />}
    >
      {day(notice.newer.date)} data {WORDS[state]}
    </Banner>
  );
}

export default SessionNoticeBanner;
