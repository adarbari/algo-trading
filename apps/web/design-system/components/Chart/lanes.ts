/**
 * Lanes under the price pane: one thin pane per lane in the chart itself, so its strips lie on
 * the chart's own time scale (the same `timeToCoordinate` as the bands and the lines, whatever
 * the business-day gaps). A lightweight-charts series primitive draws the lane's name at the left
 * and a tinted, bordered strip for each segment, from half a bar before its first session to
 * half a bar after its last. A segment's name is not drawn: the crosshair read-out, the key and
 * the hidden list in Chart.tsx carry it, so colour is never the only signal.
 */
import type { ISeriesPrimitive } from 'lightweight-charts';

import type { BandColours } from './bands';
import { bandSpan, type ChartLane, type ChartPoint } from './chartData';

/** Pixels (media): the name's row, the strip and the gap under it. A lane pane is their sum. */
export const LANE_NAME_ROW = 14;
export const LANE_STRIP = 8;
export const LANE_HEIGHT = LANE_NAME_ROW + LANE_STRIP + 2;

/** Colours and font of the lane drawing, read from the tokens of the active theme. */
export interface LaneColours {
  tints: BandColours;
  borders: BandColours;
  text: string;
  fontFamily: string;
  fontSize: number;
}

export function lanePrimitive(
  lane: ChartLane,
  points: readonly ChartPoint[],
  colours: LaneColours,
): ISeriesPrimitive {
  const spans = lane.segments.flatMap((segment) => {
    const span = bandSpan(segment, points);
    return span ? [{ ...span, tone: segment.tone }] : [];
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
          zOrder: () => 'normal',
          renderer: () => ({
            draw(target) {
              const a = x(points[0]?.time ?? '');
              const b = x(points[1]?.time ?? '');
              const half = a !== null && b !== null ? Math.abs(b - a) / 2 : 0;
              target.useBitmapCoordinateSpace(
                ({ context, bitmapSize, horizontalPixelRatio, verticalPixelRatio }) => {
                  context.fillStyle = colours.text;
                  context.font = `${String(colours.fontSize * verticalPixelRatio)}px ${colours.fontFamily}`;
                  context.textBaseline = 'top';
                  context.fillText(lane.label, 0, 0);
                  const top = Math.round(LANE_NAME_ROW * verticalPixelRatio);
                  const height = Math.round(LANE_STRIP * verticalPixelRatio);
                  const border = Math.max(1, Math.round(horizontalPixelRatio));
                  for (const span of spans) {
                    const from = x(span.from);
                    const to = x(span.to);
                    if (from === null || to === null) continue;
                    const left = Math.max(0, Math.round((from - half) * horizontalPixelRatio));
                    const right = Math.min(
                      bitmapSize.width,
                      Math.round((to + half) * horizontalPixelRatio),
                    );
                    const width = Math.max(0, right - left);
                    context.fillStyle = colours.borders[span.tone];
                    context.fillRect(left, top, width, height);
                    context.fillStyle = colours.tints[span.tone];
                    context.fillRect(
                      left + border,
                      top + border,
                      Math.max(0, width - 2 * border),
                      Math.max(0, height - 2 * border),
                    );
                  }
                },
              );
            },
          }),
        },
      ];
    },
  };
}
