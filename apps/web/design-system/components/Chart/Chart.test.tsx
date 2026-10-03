import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { Chart } from './Chart';
import { describeChart, prepare, rangeStart, rebased, tableRows } from './chartData';
import type { CrosshairInfo, EngineInput } from './engine';
import { aapl, aaplEvents, aaplVolume, msft } from './storyData';

// jsdom has no canvas: the engine (the only lightweight-charts module) is replaced by a spy.
const engine = vi.hoisted(() => ({
  draw: vi.fn(),
  cleanup: vi.fn(),
  crosshair: undefined as ((info: CrosshairInfo | null) => void) | undefined,
}));
vi.mock('./engine', () => ({
  drawChart: (
    _el: HTMLElement,
    input: EngineInput,
    _theme: unknown,
    onCrosshair: (info: CrosshairInfo | null) => void,
  ) => {
    engine.draw(input);
    engine.crosshair = onCrosshair;
    return engine.cleanup;
  },
}));

const lastInput = () => engine.draw.mock.lastCall?.[0] as EngineInput;

beforeEach(() => {
  engine.draw.mockClear();
  engine.cleanup.mockClear();
});

describe('chart data', () => {
  it('counts ranges back from the latest day and rebases to 100', () => {
    expect(rangeStart('2026-10-02', '3M')).toBe('2026-07-02');
    expect(rangeStart('2026-10-02', '1Y')).toBe('2025-10-02');
    expect(rangeStart('2026-10-02', 'All')).toBeNull();
    expect(
      rebased([
        { time: 'a', value: 50 },
        { time: 'b', value: 75 },
      ]).map((p) => p.value),
    ).toEqual([100, 150]);
  });

  it('summarises series, dates and events, and lists table rows newest first', () => {
    const chart = prepare([aapl], { range: '3M', rebase: false, events: aaplEvents });
    const text = describeChart('AAPL close', chart, {
      rebase: false,
      format: { kind: 'currency' },
    });
    expect(text).toMatch(/^AAPL close, 2 Jul 2026 to 2 Oct 2026; AAPL \$[\d.,]+ to \$333\.69/);
    expect(text).toContain('events: 1 ex-dividend, 1 earnings');
    const rows = tableRows(chart);
    expect(rows[0]?.time).toBe('2026-10-02');
    expect(rows.find((r) => r.time === '2026-08-10')?.events).toBe('Ex-dividend $0.27');
  });
});

describe('Chart', () => {
  it('is an image named by a generated summary, with a key and the windowed series drawn', async () => {
    render(<Chart label="AAPL close" series={[aapl]} range="1Y" events={aaplEvents} />);
    const image = screen.getByRole('img', { name: /^AAPL close, 2 Oct 2025 to 2 Oct 2026/ });
    expect(image).toBeInTheDocument();
    await waitFor(() => {
      expect(engine.draw).toHaveBeenCalled();
    });
    const input = lastInput();
    expect(input.series[0]?.points[0]?.time).toBe('2025-10-02');
    expect(input.series[0]?.tone).toBe('s1');
    expect(screen.getByRole('list', { name: 'Series' })).toHaveTextContent('AAPL');
    const key = screen.getByRole('list', { name: 'Event markers' });
    expect(key).toHaveTextContent('D Ex-dividend');
    expect(key).toHaveTextContent('E Earnings');
  });

  it('rebases every series to 100 and draws the reference line', async () => {
    render(<Chart label="Compare" series={[aapl, msft]} range="3M" rebase />);
    await waitFor(() => {
      expect(engine.draw).toHaveBeenCalled();
    });
    const input = lastInput();
    expect(input.rebase).toBe(true);
    expect(input.series.map((s) => s.points[0]?.value)).toEqual([100, 100]);
    expect(input.series.map((s) => s.tone)).toEqual(['s1', 's2']);
    expect(screen.getByRole('img').getAttribute('aria-label')).toContain('rebased to 100');
  });

  it('shows the crosshair read-out with formatted values, volume and events', async () => {
    render(
      <Chart label="AAPL" series={[aapl]} range="3M" events={aaplEvents} volume={aaplVolume} />,
    );
    await waitFor(() => {
      expect(engine.crosshair).toBeDefined();
    });
    act(() => {
      engine.crosshair?.({ time: '2026-08-10', x: 10, y: 20 });
    });
    const day = aapl.points.find((p) => p.time === '2026-08-10')?.value ?? 0;
    expect(screen.getByText('10 Aug 2026')).toBeInTheDocument();
    expect(screen.getByText(`$${day.toFixed(2)}`)).toBeInTheDocument();
    expect(screen.getByText('Volume')).toBeInTheDocument();
    expect(screen.getByText('D Ex-dividend · $0.27')).toBeInTheDocument();
    act(() => {
      engine.crosshair?.(null);
    });
    expect(screen.queryByText('10 Aug 2026')).toBeNull();
  });

  it('switches to a table of the same numbers and back', async () => {
    render(<Chart label="AAPL" series={[aapl]} range="3M" />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'View as table' }));
    const grid = screen.getByRole('grid', { name: 'AAPL: data' });
    expect(within(grid).getByRole('columnheader', { name: /Date/ })).toBeInTheDocument();
    const days = prepare([aapl], { range: '3M', rebase: false }).series[0]?.points.length ?? 0;
    expect(grid).toHaveAttribute('aria-rowcount', String(days + 1));
    expect(screen.queryByRole('img')).toBeNull();
    await user.click(screen.getByRole('button', { name: 'View as chart' }));
    expect(screen.getByRole('img')).toBeInTheDocument();
  });

  it('redraws when the theme changes', async () => {
    render(<Chart label="AAPL" series={[aapl]} range="3M" />);
    await waitFor(() => {
      expect(engine.draw).toHaveBeenCalledTimes(1);
    });
    document.documentElement.setAttribute('data-theme', 'light');
    await waitFor(() => {
      expect(engine.draw).toHaveBeenCalledTimes(2);
    });
    expect(engine.cleanup).toHaveBeenCalledTimes(1);
    document.documentElement.removeAttribute('data-theme');
  });

  it('shows loading, empty and error states', async () => {
    const onRetry = vi.fn();
    const { rerender } = render(<Chart label="AAPL" series={[aapl]} status="loading" />);
    expect(screen.getByRole('status')).toHaveTextContent('Loading AAPL');
    rerender(<Chart label="AAPL" series={[]} emptyMessage="No prices yet" />);
    expect(screen.getByText('No prices yet')).toBeInTheDocument();
    rerender(<Chart label="AAPL" series={[aapl]} status="error" onRetry={onRetry} />);
    expect(screen.getByRole('alert')).toHaveTextContent('The chart could not load.');
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(onRetry).toHaveBeenCalledOnce();
    expect(engine.draw).not.toHaveBeenCalled();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <Chart label="AAPL" series={[aapl, msft]} range="3M" rebase events={aaplEvents} />,
    );
    await expectNoA11yViolations(container);
  });
});
