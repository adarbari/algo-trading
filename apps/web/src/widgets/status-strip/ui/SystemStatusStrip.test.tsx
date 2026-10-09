import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { SystemIssue } from '@/entities/system-status';
import { expectNoA11yViolations } from '@/shared/lib/testing';

import { SystemStatusStrip } from './SystemStatusStrip';

const hooks = vi.hoisted(() => ({ useSystemIssues: vi.fn() }));
vi.mock('@/entities/system-status', () => ({ useSystemIssues: hooks.useSystemIssues }));

const ISSUES: SystemIssue[] = [
  {
    id: 'nightly:r1:FAILED',
    severity: 'failing',
    title: 'Nightly run 2026-10-08 failed',
    detail: 'steps not complete',
    links: [{ label: 'View run', href: '/admin/ingestion' }],
  },
  { id: 'screen:s1', severity: 'warning', title: 'Screener "A" has no run', links: [] },
];

beforeEach(() => {
  hooks.useSystemIssues.mockReset();
});
afterEach(() => {
  localStorage.clear();
});

describe('SystemStatusStrip', () => {
  it('asks for the admin read only for an admin and shows the summary', () => {
    hooks.useSystemIssues.mockReturnValue(ISSUES);
    render(<SystemStatusStrip admin />);
    expect(hooks.useSystemIssues).toHaveBeenCalledWith(true);
    expect(screen.getByText('1 failing')).toBeInTheDocument();
    expect(screen.getByText('and 1 more')).toBeInTheDocument();
  });

  it('renders nothing when the system is clear', () => {
    hooks.useSystemIssues.mockReturnValue([]);
    const { container } = render(<SystemStatusStrip admin={false} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('lists the issues with their links, and a snoozed one is gone and stays gone', async () => {
    hooks.useSystemIssues.mockReturnValue(ISSUES);
    const { unmount } = render(<SystemStatusStrip admin />);
    await userEvent.click(screen.getByRole('button', { name: /1 failing/ }));
    expect(screen.getByRole('link', { name: 'View run' })).toHaveAttribute(
      'href',
      '/admin/ingestion',
    );
    await userEvent.click(
      screen.getAllByRole('button', { name: 'Snooze 24h' }).at(0) as HTMLElement,
    );
    expect(screen.queryByText('1 failing')).not.toBeInTheDocument();
    expect(screen.getByText('1 warning')).toBeInTheDocument();
    unmount();
    render(<SystemStatusStrip admin />);
    expect(screen.queryByText('1 failing')).not.toBeInTheDocument();
  });

  it('has no accessibility violations', async () => {
    hooks.useSystemIssues.mockReturnValue(ISSUES);
    const { container } = render(<SystemStatusStrip admin />);
    await expectNoA11yViolations(container);
  });
});
