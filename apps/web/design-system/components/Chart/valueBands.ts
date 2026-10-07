/**
 * Shaded value bands behind the chart's series: a lightweight-charts series primitive that fills
 * the horizontal span between two prices across the whole price pane (an open edge runs to the
 * pane's top or bottom), in a flat tint from the status tokens. Drawn in the bottom layer. The
 * band's name is not drawn: the key and the hidden list in Chart.tsx carry it, so colour is never
 * the only signal.
 */
import type { ISeriesApi, ISeriesPrimitive } from 'lightweight-charts';

import type { BandColours } from './bands';
import type { ChartValueBand } from './chartData';

export function valueBandsPrimitive(
  bands: readonly ChartValueBand[],
  colours: BandColours,
): ISeriesPrimitive {
  let series: ISeriesApi<'Line' | 'Area'> | undefined;
  let requestUpdate: (() => void) | undefined;
  return {
    attached(param) {
      series = param.series as ISeriesApi<'Line' | 'Area'>;
      requestUpdate = param.requestUpdate;
      requestUpdate();
    },
    detached() {
      series = undefined;
      requestUpdate = undefined;
    },
    paneViews() {
      return [
        {
          zOrder: () => 'bottom',
          renderer: () => ({
            draw(target) {
              target.useBitmapCoordinateSpace(({ context, bitmapSize, verticalPixelRatio }) => {
                for (const band of bands) {
                  // Larger prices are higher up, so `to` is the band's top edge.
                  const top = band.to === undefined ? 0 : series?.priceToCoordinate(band.to);
                  const bottom =
                    band.from === undefined
                      ? bitmapSize.height
                      : series?.priceToCoordinate(band.from);
                  if (top === null || top === undefined) continue;
                  if (bottom === null || bottom === undefined) continue;
                  const y1 = band.to === undefined ? 0 : Math.round(top * verticalPixelRatio);
                  const y2 =
                    band.from === undefined
                      ? bitmapSize.height
                      : Math.round(bottom * verticalPixelRatio);
                  context.fillStyle = colours[band.tone];
                  context.fillRect(0, y1, bitmapSize.width, Math.max(0, y2 - y1));
                }
              });
            },
          }),
        },
      ];
    },
  };
}
