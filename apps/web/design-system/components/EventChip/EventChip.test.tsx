import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { cpi, expectNoA11yViolations, oneOfEach } from '../../testing';
import { EventChip } from './EventChip';
import { EVENT_KIND_NAMES, EVENT_KINDS, timeText } from './eventKinds';

describe('EventChip', () => {
  it('is static text with the kind named for screen readers', () => {
    render(<EventChip kind="macro_release" label="CPI" />);
    expect(screen.getByText('CPI')).toBeInTheDocument();
    expect(screen.getByText('Macro release:')).toBeInTheDocument();
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('names every kind in words', () => {
    for (const kind of EVENT_KINDS) {
      const { unmount } = render(<EventChip kind={kind} label="x" />);
      expect(screen.getByText(`${EVENT_KIND_NAMES[kind]}:`)).toBeInTheDocument();
      unmount();
    }
  });

  it('shows the time, source and known-from in a tooltip on focus', async () => {
    render(<EventChip kind={cpi.kind} label={cpi.label} event={cpi} />);
    await userEvent.tab();
    const tip = await screen.findByRole('tooltip');
    expect(tip).toHaveTextContent('CPI');
    expect(tip).toHaveTextContent('Wed 14 Oct, 08:30');
    expect(tip).toHaveTextContent('Source: BLS');
    expect(tip).toHaveTextContent('Known from 5 Jan 2026');
  });

  it('reads time codes as words and leaves release times as they are', () => {
    expect(timeText('after_hours')).toBe('after the close');
    expect(timeText('pre_market')).toBe('before the open');
    expect(timeText('08:30')).toBe('08:30');
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <>
        {oneOfEach.map((event) => (
          <EventChip key={event.label} kind={event.kind} label={event.label} event={event} />
        ))}
        <EventChip kind="filing" label="8.01 other" />
      </>,
    );
    await expectNoA11yViolations(container);
  });
});
