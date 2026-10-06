/**
 * Shaded bands behind the chart's series: a lightweight-charts series primitive that fills a
 * vertical span of the price pane for each band, from half a bar before its first session to half
 * a bar after its last (neighbouring bands meet without a gap), in a flat tint from the status
 * tokens, or, for a `hatch` band, in diagonal lines of the tone's solid colour (no fill, so bands
 * that overlap stay readable and colour is not the only signal). Drawn in the bottom layer, under the grid and the lines. The band's name is not drawn:
 * the key and the hidden list in Chart.tsx carry it, so colour is never the only signal.
 */
import type { ISeriesPrimitive } from 'lightweight-charts';

import { bandSpan, type ChartBand, type ChartBandTone, type ChartPoint } from './chartData';

/** Band tints per tone, read from the tokens of the active theme (see chartTheme.ts). */
export type BandColours = Record<ChartBandTone, string>;

/** Spacing of the hatch lines, in CSS px (one tile of the pattern). */
const HATCH = 6;

/** A repeating diagonal-line pattern in `colour`, one tile at the device pixel ratio. */
function hatchPattern(context: CanvasRenderingContext2D, colour: string, ratio: number) {
  const size = Math.round(HATCH * ratio);
  const tile = document.createElement('canvas');
  tile.width = size;
  tile.height = size;
  const pen = tile.getContext('2d');
  if (!pen) return colour;
  pen.strokeStyle = colour;
  pen.lineWidth = Math.max(1, Math.round(ratio));
  pen.beginPath();
  // Lines running up to the right; the extra corners make the lines meet across tiles.
  pen.moveTo(-size, size * 2);
  pen.lineTo(size * 2, -size);
  pen.moveTo(-size, size);
  pen.lineTo(size, -size);
  pen.moveTo(0, size * 2);
  pen.lineTo(size * 2, 0);
  pen.stroke();
  return context.createPattern(tile, 'repeat') ?? colour;
}

export function bandsPrimitive(
  bands: readonly ChartBand[],
  points: readonly ChartPoint[],
  colours: BandColours,
  lines: BandColours,
): ISeriesPrimitive {
  const spans = bands.flatMap((band) => {
    const span = bandSpan(band, points);
    return span ? [{ ...span, tone: band.tone, hatch: band.pattern === 'hatch' }] : [];
  });
  let chart: Parameters<NonNullable<ISeriesPrimitive['attached']>>[0]['chart'] | undefined;
  let requestUpdate: (() => void) | undefined;

  /** Pixels (media) of a session's x, or null while it is outside the drawn range. */
  const x = (day: string): number | null => chart?.timeScale().timeToCoordinate(day) ?? null;

  return {
    attached(param) {
      chart = param.chart;
      requestUpdate = param.requestUpdate;
      requestUpdate();
    },
    detached() {
      chart = undefined;
      requestUpdate = undefined;
    },
    paneViews() {
      return [
        {
          zOrder: () => 'bottom',
          renderer: () => ({
            draw(target) {
              const a = x(points[0]?.time ?? '');
              const b = x(points[1]?.time ?? '');
              // Half the distance between two sessions: the edge of a band lies between bars.
              const half = a !== null && b !== null ? Math.abs(b - a) / 2 : 0;
              target.useBitmapCoordinateSpace(({ context, bitmapSize, horizontalPixelRatio }) => {
                for (const span of spans) {
                  const from = x(span.from);
                  const to = x(span.to);
                  if (from === null || to === null) continue;
                  const left = Math.max(0, Math.round((from - half) * horizontalPixelRatio));
                  const right = Math.min(
                    bitmapSize.width,
                    Math.round((to + half) * horizontalPixelRatio),
                  );
                  context.fillStyle = span.hatch
                    ? hatchPattern(context, lines[span.tone], horizontalPixelRatio)
                    : colours[span.tone];
                  context.fillRect(left, 0, Math.max(0, right - left), bitmapSize.height);
                }
              });
            },
          }),
        },
      ];
    },
  };
}
