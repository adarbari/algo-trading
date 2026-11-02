import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { CalendarPage } from './CalendarPage';

vi.mock('@/widgets/event-calendar-panel', async () => {
  const { Text } = await import('@algotrade/ui');
  return {
    EventCalendarPanel: () => <Text>calendar panel</Text>,
    MacroCalendar: () => <Text>macro view</Text>,
  };
});

vi.mock('./EarningsWeek', async () => {
  const { Text } = await import('@algotrade/ui');
  return { EarningsWeek: () => <Text>week view</Text> };
});

describe('CalendarPage', () => {
  it('opens on the earnings week and switches between the three views', async () => {
    render(<CalendarPage />);
    expect(screen.getByRole('heading', { level: 1, name: 'Calendar' })).toBeInTheDocument();
    expect(screen.getByText('week view')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('tab', { name: 'Next 90 days' }));
    expect(screen.getByText('calendar panel')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('tab', { name: 'Macro' }));
    expect(screen.getByText('macro view')).toBeInTheDocument();
  });
});
