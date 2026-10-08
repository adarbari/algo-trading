import { beforeEach, describe, expect, it, vi } from 'vitest';

import { prepare } from './chartData';
import { readTheme } from './chartTheme';
import { drawChart, type EngineInput } from './engine';
import { aapl } from './storyData';

// jsdom has no canvas: lightweight-charts is replaced by a recording fake.
const fake = vi.hoisted(() => {
  let range: { from: number; to: number } | null = null;
  const timeScale = {
    fitContent: vi.fn(() => {
      range = null;
    }),
    getVisibleLogicalRange: vi.fn(() => range),
    setVisibleLogicalRange: vi.fn((next: { from: number; to: number }) => {
      range = next;
    }),
  };
  const series = () => ({
    setData: vi.fn(),
    createPriceLine: vi.fn(),
    attachPrimitive: vi.fn(),
  });
  const chart = {
    addSeries: vi.fn(series),
    panes: vi.fn(() => []),
    timeScale: () => timeScale,
    subscribeCrosshairMove: vi.fn(),
    remove: vi.fn(),
  };
  return {
    chart,
    timeScale,
    createChart: vi.fn(() => chart),
    setRange: (next: { from: number; to: number } | null) => {
      range = next;
    },
  };
});
vi.mock('lightweight-charts', () => ({
  AreaSeries: 'Area',
  LineSeries: 'Line',
  HistogramSeries: 'Histogram',
  ColorType: { Solid: 'solid' },
  CrosshairMode: { Magnet: 1 },
  LineStyle: { Solid: 0, Dashed: 2 },
  createChart: fake.createChart,
  createSeriesMarkers: vi.fn(),
}));

/** One series over `days` consecutive days. */
function input(days: number): EngineInput {
  const chart = prepare([{ ...aapl, points: aapl.points.slice(-days) }], {
    range: 'All',
    rebase: false,
  });
  return {
    type: 'line',
    series: chart.series,
    events: [],
    bands: [],
    lanes: [],
    referenceLines: [],
    valueBands: [],
    volume: [],
    rebase: false,
    formatValue: String,
    formatVolume: String,
  };
}

const draw = (days = 100) =>
  drawChart(document.createElement('div'), input(days), readTheme(document.body), () => {});

beforeEach(() => {
  vi.clearAllMocks();
  fake.setRange(null);
});

describe('drawChart', () => {
  it('pans and pinches on touch but leaves the mouse wheel and drags to the page', () => {
    draw();
    expect(fake.createChart).toHaveBeenCalledWith(
      expect.any(HTMLElement),
      expect.objectContaining({
        handleScale: {
          pinch: true,
          mouseWheel: false,
          axisPressedMouseMove: false,
          axisDoubleClickReset: false,
        },
        handleScroll: {
          horzTouchDrag: true,
          vertTouchDrag: false,
          mouseWheel: false,
          pressedMouseMove: false,
        },
        kineticScroll: { mouse: false, touch: true },
        timeScale: expect.objectContaining({ fixLeftEdge: true, fixRightEdge: true }) as unknown,
      }),
    );
  });

  it('zooms around the centre of the visible window', () => {
    const chart = draw(100);
    fake.setRange({ from: 20, to: 60 });
    chart.zoom(0.5);
    expect(fake.timeScale.setVisibleLogicalRange).toHaveBeenLastCalledWith({ from: 30, to: 50 });
  });

  it('keeps a zoom inside the data and never closer than a few days', () => {
    const chart = draw(100);
    fake.setRange({ from: 80, to: 99 });
    chart.zoom(2);
    expect(fake.timeScale.setVisibleLogicalRange).toHaveBeenLastCalledWith({ from: 61, to: 99 });
    fake.setRange({ from: 0, to: 2 });
    chart.zoom(0.5);
    expect(fake.timeScale.setVisibleLogicalRange).toHaveBeenLastCalledWith({ from: 0, to: 4 });
  });

  it('shows the whole window when zoomed out past it, on reset, and removes the chart', () => {
    const chart = draw(100);
    fake.setRange({ from: 10, to: 90 });
    fake.timeScale.fitContent.mockClear();
    chart.zoom(2);
    expect(fake.timeScale.fitContent).toHaveBeenCalledOnce();
    chart.reset();
    expect(fake.timeScale.fitContent).toHaveBeenCalledTimes(2);
    chart.dispose();
    expect(fake.chart.remove).toHaveBeenCalledOnce();
  });
});
