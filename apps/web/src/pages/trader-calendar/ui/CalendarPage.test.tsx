import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { CalendarPage } from './CalendarPage';

vi.mock('@/widgets/event-calendar-panel', async () => {
  const { Text } = await import('@algotrade/ui');
  return { EventCalendarPanel: () => <Text>calendar panel</Text> };
});

describe('CalendarPage', () => {
  it('has its heading and the calendar', () => {
    render(<CalendarPage />);
    expect(screen.getByRole('heading', { level: 1, name: 'Calendar' })).toBeInTheDocument();
    expect(screen.getByText('calendar panel')).toBeInTheDocument();
  });
});
