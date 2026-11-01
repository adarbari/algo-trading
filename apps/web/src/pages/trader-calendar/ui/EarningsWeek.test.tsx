import { Text } from '@algotrade/ui';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { CALENDAR_FIXTURE } from '@/entities/event';
import { fakeQuery } from '@/shared/lib/testing';

import { EarningsWeek } from './EarningsWeek';

const hooks = vi.hoisted(() => ({
  useEventCalendar: vi.fn(),
  table: vi.fn<(props: { columns: string[] }) => void>(),
}));

vi.mock('@/entities/event', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useEventCalendar: hooks.useEventCalendar,
}));
vi.mock('@/features/calendar-source', () => ({
  useCalendarSource: () => ({
    value: 'scope',
    setValue: vi.fn(),
    screeners: [],
    scope: true,
    ids: [],
    ready: true,
    message: null,
    loading: false,
    failed: false,
  }),
  CalendarSourcePicker: () => null,
}));
vi.mock('@/widgets/feature-table', () => ({
  FeatureTable: (props: { label: string; keys: string[]; columns: string[] }) => {
    hooks.table(props);
    return <Text>{`${props.label} | ${props.keys.join(',')}`}</Text>;
  },
}));

beforeEach(() => {
  hooks.useEventCalendar.mockReturnValue(fakeQuery(CALENDAR_FIXTURE));
});

describe('EarningsWeek', () => {
  it('asks the feature table for the reporters, with the priced and the usual move', () => {
    render(<EarningsWeek />);
    expect(screen.getByText(/Earnings · .* to .* \| AAPL/)).toBeInTheDocument();
    const columns = hooks.table.mock.calls[0]?.[0].columns ?? [];
    expect(columns).toContain('rollup.implied_move@v1.implied_move');
    expect(columns).toContain('rollup.earnings_moves@v1.abs_move_mean_12');
  });
});
