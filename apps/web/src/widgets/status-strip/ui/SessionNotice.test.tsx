import { Button } from '@algotrade/ui';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { SessionNotice as Notice } from '@/entities/system-status';
import { expectNoA11yViolations } from '@/shared/lib/testing';

import { SessionNotice } from './SessionNotice';

const hooks = vi.hoisted(() => ({ useSessionNotice: vi.fn() }));
vi.mock('@/entities/system-status', () => ({ useSessionNotice: hooks.useSessionNotice }));
vi.mock('@/features/guide-help', () => ({
  GuideHelp: ({ entry }: { entry: { kind: string; id: string } }) => (
    <Button size="sm">{`Help: ${entry.kind}/${entry.id}`}</Button>
  ),
}));

const notice = (state: Notice['newer']['state']): Notice => ({
  served: '2026-10-09',
  newer: { date: '2026-10-10', state, kind: state === 'FAILED_RETRYING' ? 'SYSTEM' : null },
});

beforeEach(() => {
  hooks.useSessionNotice.mockReset();
});

describe('SessionNotice', () => {
  it('says which close is shown and that the newer data is still processing', async () => {
    hooks.useSessionNotice.mockReturnValue(notice('IN_PROGRESS'));
    const { container } = render(<SessionNotice admin={false} />);
    expect(hooks.useSessionNotice).toHaveBeenCalledWith(false);
    expect(screen.getByText('Showing 9 Oct 2026 close')).toBeInTheDocument();
    expect(screen.getByText(/10 Oct 2026 data still processing/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Help: term/last_complete_session' })).toBeVisible();
    await expectNoA11yViolations(container);
  });

  it('says a failed session is being retried, never which step failed', () => {
    hooks.useSessionNotice.mockReturnValue(notice('FAILED_RETRYING'));
    render(<SessionNotice admin />);
    expect(screen.getByText(/10 Oct 2026 data failed and is being retried/)).toBeInTheDocument();
  });

  it('renders nothing when the page shows the newest session', () => {
    hooks.useSessionNotice.mockReturnValue(null);
    const { container } = render(<SessionNotice admin />);
    expect(container).toBeEmptyDOMElement();
  });
});
