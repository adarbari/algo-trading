import { Button } from '@algotrade/ui';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { SessionNotice as Notice } from '@/entities/system-status';
import { expectNoA11yViolations } from '@/shared/lib/testing';

import { SessionNoticeBanner } from './SessionNoticeBanner';

vi.mock('@/features/guide-help', () => ({
  GuideHelp: ({ entry }: { entry: { kind: string; id: string } }) => (
    <Button size="sm">{`Help: ${entry.kind}/${entry.id}`}</Button>
  ),
}));

const notice = (state: NonNullable<Notice['newer']>['state']): Notice => ({
  date: '2026-10-09',
  newer: { date: '2026-10-10', state },
});

describe('SessionNoticeBanner', () => {
  it('says which close is shown and that the newer data is still processing', async () => {
    const { container } = render(<SessionNoticeBanner notice={notice('IN_PROGRESS')} />);
    expect(screen.getByText('Showing 9 Oct 2026 close')).toBeInTheDocument();
    expect(screen.getByText(/10 Oct 2026 data still processing/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Help: term/last_complete_session' })).toBeVisible();
    await expectNoA11yViolations(container);
  });

  it('says a failed session is being retried, never which step failed', async () => {
    render(<SessionNoticeBanner notice={notice('FAILED_RETRYING')} />);
    expect(
      await screen.findByText(/10 Oct 2026 data failed and is being retried/),
    ).toBeInTheDocument();
  });
});
