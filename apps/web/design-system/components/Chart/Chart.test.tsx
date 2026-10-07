import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { Chart } from './Chart';
import {
  bandSpan,
  clampBands,
  describeChart,
  prepare,
  rangeStart,
  rebased,
  tableRows,
} from './chartData';
import type { CrosshairInfo, EngineInput } from './engine';
import {
  aapl,
  aaplEvents,
  eventMarkers,
  aaplVolume,
  cautionBand,
  msft,
  sampleBands,
  sampleLanes,
  sampleReferenceLines,
  sampleValueBands,
  stressBand,
} from './storyData';

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

describe('chart event markers', () => {
  it('counts filings and macro releases in the summary and lists them in the table', () => {
    const chart = prepare([aapl], { range: '1Y', rebase: false, events: eventMarkers });
    const text = describeChart('AAPL close', chart, {
      rebase: false,
      format: { kind: 'currency' },
    });
    expect(text).toContain('4 earnings, 4 filing, 4 macro release');
    const rows = tableRows(chart);
    expect(rows.find((r) => r.time === '2026-01-29')?.events).toBe(
      'Earnings after close; Filing 8-K 2.02 results',
    );
    expect(rows.find((r) => r.time === '2026-05-12')?.events).toBe('Macro release CPI 08:30');
  });
});

describe('chart bands', () => {
  it('cuts bands to the window and drops those outside it', () => {
    const outside = {
      start: '2020-03-01',
      end: '2020-04-01',
      tone: 'negative',
      label: 'Old',
    } as const;
    const straddling = {
      start: '2025-06-01',
      end: '2025-11-03',
      tone: 'warning',
      label: 'Edge',
    } as const;
    expect(
      clampBands([outside, straddling, stressBand, cautionBand], '2025-10-02', '2026-10-02').map(
        (b) => [b.label, b.start, b.end],
      ),
    ).toEqual([
      ['Edge', '2025-10-02', '2025-11-03'],
      ['Caution', '2026-01-12', '2026-02-20'],
      ['Stress', '2026-02-21', '2026-03-27'],
    ]);
    expect(clampBands([stressBand], null, null)).toEqual([]);
    expect(
      clampBands(
        [{ ...stressBand, start: '2026-03-27', end: '2026-02-21' }],
        '2025-10-02',
        '2026-10-02',
      ),
    ).toEqual([]);
  });

  it('shades the sessions inside a band, so a weekend edge starts on the next session', () => {
    // 21 Feb 2026 is a Saturday: the band's first session is Monday the 23rd.
    expect(bandSpan(stressBand, aapl.points)).toEqual({ from: '2026-02-23', to: '2026-03-27' });
    expect(
      bandSpan({ ...stressBand, start: '2026-02-21', end: '2026-02-22' }, aapl.points),
    ).toBeUndefined();
  });

  it('lists a band per row in the table by label', () => {
    const chart = prepare([aapl], { range: '1Y', rebase: false, bands: sampleBands });
    const rows = tableRows(chart);
    expect(rows.find((r) => r.time === '2026-03-02')?.shaded).toBe('Stress');
    expect(rows.find((r) => r.time === '2026-06-01')?.shaded).toBe('');
    expect(describeChart('AAPL', chart, { rebase: false, format: { kind: 'currency' } })).toContain(
      '3 shaded periods',
    );
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

  it('keys filing and macro markers and reads their text in the crosshair', async () => {
    render(<Chart label="AAPL close" series={[aapl]} range="1Y" events={eventMarkers} />);
    const key = screen.getByRole('list', { name: 'Event markers' });
    expect(key).toHaveTextContent('E Earnings');
    expect(key).toHaveTextContent('F Filing');
    expect(key).toHaveTextContent('M Macro release');
    await waitFor(() => {
      expect(engine.crosshair).toBeDefined();
    });
    act(() => {
      engine.crosshair?.({ time: '2026-07-30', x: 10, y: 20 });
    });
    expect(screen.getByText('F Filing · 8-K 2.02 results')).toBeInTheDocument();
    expect(screen.getByText('E Earnings · after close')).toBeInTheDocument();
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

  it('formats the volume pane as a compact count and the price as currency', async () => {
    render(<Chart label="AAPL" series={[aapl]} volume={aaplVolume} />);
    await waitFor(() => {
      expect(engine.draw).toHaveBeenCalled();
    });
    const input = lastInput();
    expect(input.formatVolume(800_000_000)).toBe('800M');
    expect(input.formatVolume(11_400)).toBe('11.4K');
    expect(input.formatValue(333.69)).toBe('$333.69');
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

  it('passes bands to the engine and names them in a key and a list for screen readers', async () => {
    render(<Chart label="AAPL" series={[aapl]} range="1Y" bands={sampleBands} />);
    await waitFor(() => {
      expect(engine.draw).toHaveBeenCalled();
    });
    expect(lastInput().bands).toHaveLength(3);
    const key = screen.getByRole('list', { name: 'Shaded periods' });
    expect(
      within(key)
        .getAllByRole('listitem')
        .map((li) => li.textContent),
    ).toEqual(['Caution', 'Stress']);
    const list = screen.getByRole('list', { name: 'AAPL: shaded periods' });
    expect(within(list).getAllByRole('listitem')[1]).toHaveTextContent(
      'Stress: 21 Feb 2026 to 27 Mar 2026',
    );
  });

  it('can hide the bands from the key but keeps the list for screen readers', () => {
    render(<Chart label="AAPL" series={[aapl]} bands={sampleBands} bandKey={false} />);
    expect(screen.queryByRole('list', { name: 'Shaded periods' })).toBeNull();
    expect(screen.getByRole('list', { name: 'AAPL: shaded periods' })).toBeInTheDocument();
  });

  it('adds a Shaded column to the table when there are bands', async () => {
    render(<Chart label="AAPL" series={[aapl]} range="1Y" bands={sampleBands} />);
    await userEvent.click(screen.getByRole('button', { name: 'View as table' }));
    expect(screen.getByRole('columnheader', { name: /Shaded/ })).toBeInTheDocument();
  });

  it('is unchanged without bands: no key, no list, no engine bands', async () => {
    render(<Chart label="AAPL" series={[aapl]} range="1Y" />);
    await waitFor(() => {
      expect(engine.draw).toHaveBeenCalled();
    });
    expect(lastInput().bands).toEqual([]);
    expect(screen.queryByRole('list', { name: 'Shaded periods' })).toBeNull();
    expect(screen.queryByRole('list', { name: 'AAPL: shaded periods' })).toBeNull();
  });

  it('passes reference lines to the engine and lists them for screen readers', async () => {
    render(<Chart label="AAPL" series={[aapl]} range="1Y" referenceLines={sampleReferenceLines} />);
    await waitFor(() => {
      expect(engine.draw).toHaveBeenCalled();
    });
    expect(lastInput().referenceLines).toEqual(sampleReferenceLines);
    const list = screen.getByRole('list', { name: 'AAPL: reference lines' });
    expect(
      within(list)
        .getAllByRole('listitem')
        .map((li) => li.textContent),
    ).toEqual(['Floor: $300.00', 'Target: $340.00']);
    expect(screen.getByRole('img').getAttribute('aria-label')).toContain(
      'reference lines: Floor $300.00, Target $340.00',
    );
  });

  it('passes value bands to the engine, keys and lists them, and drops an empty one', async () => {
    render(
      <Chart
        label="AAPL"
        series={[aapl]}
        range="1Y"
        valueBands={[
          ...sampleValueBands,
          { from: 340, to: 330, tone: 'accent', label: 'Backwards' },
          { tone: 'accent', label: 'No edge' },
        ]}
      />,
    );
    await waitFor(() => {
      expect(engine.draw).toHaveBeenCalled();
    });
    expect(lastInput().valueBands).toEqual(sampleValueBands);
    const list = screen.getByRole('list', { name: 'AAPL: shaded value zones' });
    expect(
      within(list)
        .getAllByRole('listitem')
        .map((li) => li.textContent),
    ).toEqual(['Below the floor: below $300.00']);
    expect(screen.getByRole('img').getAttribute('aria-label')).toContain(
      'shaded value zone: Below the floor below $300.00',
    );
    expect(screen.getAllByText('Below the floor').length).toBeGreaterThan(0);
  });

  it('describes a closed value band by both edges', () => {
    const chart = prepare([aapl], {
      range: '1Y',
      rebase: false,
      valueBands: [{ from: 0, to: 0.1, tone: 'accent', label: 'Squeeze' }],
    });
    const text = describeChart('AAPL', chart, {
      rebase: false,
      format: { kind: 'number', digits: 2 },
    });
    expect(text).toContain('shaded value zone: Squeeze from 0.00 to 0.10');
  });

  it('drops a reference line without a finite value', async () => {
    render(
      <Chart
        label="AAPL"
        series={[aapl]}
        referenceLines={[{ value: Number.NaN }, { value: 310 }]}
      />,
    );
    await waitFor(() => {
      expect(engine.draw).toHaveBeenCalled();
    });
    expect(lastInput().referenceLines).toEqual([{ value: 310 }]);
  });

  it('passes lanes to the engine, keyed by distinct segment labels and listed for screen readers', async () => {
    render(<Chart label="AAPL" series={[aapl]} range="1Y" lanes={sampleLanes} />);
    await waitFor(() => {
      expect(engine.draw).toHaveBeenCalled();
    });
    expect(lastInput().lanes.map((l) => l.id)).toEqual(['trend', 'volatility']);
    expect(lastInput().lanes[0]?.segments).toHaveLength(3);
    const trend = screen.getByRole('list', { name: 'AAPL: Trend' });
    expect(within(trend).getAllByRole('listitem')).toHaveLength(3);
    expect(within(trend).getAllByRole('listitem')[1]).toHaveTextContent(
      'Falling: 12 Jan 2026 to 27 Mar 2026',
    );
    expect(screen.getByRole('list', { name: 'AAPL: Volatility' })).toBeInTheDocument();
    const key = screen.getByRole('list', { name: 'Lane states' });
    expect(
      within(key)
        .getAllByRole('listitem')
        .map((li) => li.textContent),
    ).toEqual(['Rising', 'Falling', 'Elevated']);
    expect(screen.getByRole('img').getAttribute('aria-label')).toContain(
      'lanes under the axis: Trend, Volatility',
    );
  });

  it('cuts lane segments to the window and reads the covering segment in the crosshair', async () => {
    render(<Chart label="AAPL" series={[aapl]} range="3M" lanes={sampleLanes} />);
    await waitFor(() => {
      expect(engine.crosshair).toBeDefined();
    });
    expect(lastInput().lanes[0]?.segments).toHaveLength(1);
    act(() => {
      engine.crosshair?.({ time: '2026-09-01', x: 10, y: 20 });
    });
    const readout = screen.getByText(/^1 Sep/).parentElement as HTMLElement;
    expect(within(readout).getByText('Trend')).toBeInTheDocument();
    expect(within(readout).getByText('Rising')).toBeInTheDocument();
    expect(within(readout).getByText('Elevated')).toBeInTheDocument();
  });

  it('hatches a band and keys it apart from the solid ones', async () => {
    render(
      <Chart
        label="AAPL"
        series={[aapl]}
        range="1Y"
        bands={[{ ...stressBand, pattern: 'hatch', label: 'Recession' }, cautionBand]}
      />,
    );
    await waitFor(() => {
      expect(engine.draw).toHaveBeenCalled();
    });
    expect(lastInput().bands.map((b) => b.pattern)).toEqual([undefined, 'hatch']);
    expect(
      within(screen.getByRole('list', { name: 'Shaded periods' })).getByText('Caution'),
    ).toBeInTheDocument();
    const hatched = screen.getByRole('list', { name: 'Hatched periods' });
    expect(hatched).toHaveTextContent('Recession');
    expect(hatched.querySelector('[data-swatch="hatch"]')).not.toBeNull();
  });

  it('breaks the line at a null value and leaves it out of the summary and the table', async () => {
    const gap = {
      ...aapl,
      points: aapl.points.map((p) => (p.time === '2026-09-15' ? { ...p, value: null } : p)),
    };
    render(<Chart label="AAPL" series={[gap]} range="3M" />);
    await waitFor(() => {
      expect(engine.draw).toHaveBeenCalled();
    });
    expect(lastInput().series[0]?.points.find((p) => p.time === '2026-09-15')?.value).toBeNull();
    expect(screen.getByRole('img').getAttribute('aria-label')).toContain('low $');
    await userEvent.click(screen.getByRole('button', { name: 'View as table' }));
    expect(screen.getByRole('grid', { name: 'AAPL: data' })).toBeInTheDocument();
  });

  it('rebases around a gap and never rebases a gap into a number', () => {
    expect(
      rebased([
        { time: 'a', value: null },
        { time: 'b', value: 50 },
        { time: 'c', value: 75 },
      ]).map((p) => p.value),
    ).toEqual([null, 100, 150]);
  });

  it('adds a column per lane to the table', async () => {
    render(<Chart label="AAPL" series={[aapl]} range="1Y" lanes={sampleLanes} />);
    await userEvent.click(screen.getByRole('button', { name: 'View as table' }));
    expect(screen.getByRole('columnheader', { name: /Trend/ })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: /Volatility/ })).toBeInTheDocument();
    expect(document.querySelector('[data-lanes]')).toBeNull();
  });

  it('is unchanged without reference lines or lanes', async () => {
    render(<Chart label="AAPL" series={[aapl]} range="1Y" />);
    await waitFor(() => {
      expect(engine.draw).toHaveBeenCalled();
    });
    expect(lastInput().referenceLines).toEqual([]);
    expect(document.querySelector('[data-lanes]')).toBeNull();
    expect(screen.queryByRole('list', { name: 'AAPL: reference lines' })).toBeNull();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <Chart
        label="AAPL"
        series={[aapl, msft]}
        range="1Y"
        rebase
        events={aaplEvents}
        bands={sampleBands}
        lanes={sampleLanes}
        referenceLines={sampleReferenceLines}
      />,
    );
    await expectNoA11yViolations(container);
  });
});
