import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { CALENDAR_FIXTURE } from '@/entities/event';
import { expectNoA11yViolations, fakeQuery, stubElementSize } from '@/shared/lib/testing';

import { MacroDays } from './MacroDays';

const hooks = vi.hoisted(() => ({ useEventCalendar: vi.fn() }));
vi.mock('@/entities/event', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useEventCalendar: hooks.useEventCalendar,
}));

vi.mock('@/features/guide-help', () => ({ termHelp: () => null }));

stubElementSize();

describe('MacroDays', () => {
  it('lists the market-wide days only', async () => {
    hooks.useEventCalendar.mockReturnValue(fakeQuery(CALENDAR_FIXTURE));
    const { container } = render(<MacroDays />);
    expect(screen.getByRole('list', { name: /Market-wide events/ })).toBeInTheDocument();
    expect(screen.queryByText('AAPL')).not.toBeInTheDocument();
    await expectNoA11yViolations(container);
  });
});
