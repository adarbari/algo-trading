/**
 * The row heights the virtualizer needs in pixels, read from the tokens on the table's element
 * (`--density-row-height`; a two-line row adds one `--line-height-xs`, matching the CSS) and
 * re-read when UiProvider switches density (`data-density` on <html>). Rows have this fixed
 * height, so 11k rows scroll with stable positions and no per-row measurement.
 */
import { useLayoutEffect, useState, type RefObject } from 'react';

/** Compact density's row height: the fallback where CSS is not computed (unit tests). */
export const FALLBACK_ROW_HEIGHT = 28;
/** The xs line height (a two-line row's second line) where CSS is not computed. */
export const FALLBACK_LINE_HEIGHT = 16;

export interface RowHeights {
  /** One-line row (also the header row). */
  base: number;
  /** A body row with `lines` lines. */
  row: number;
}

function px(element: Element, token: string, fallback: number): number {
  const value = Number.parseFloat(getComputedStyle(element).getPropertyValue(token));
  return Number.isFinite(value) && value > 0 ? value : fallback;
}

function read(element: Element | null, lines: number): RowHeights {
  const base = element
    ? px(element, '--density-row-height', FALLBACK_ROW_HEIGHT)
    : FALLBACK_ROW_HEIGHT;
  const line = element
    ? px(element, '--line-height-xs', FALLBACK_LINE_HEIGHT)
    : FALLBACK_LINE_HEIGHT;
  return { base, row: base + (lines - 1) * line };
}

export function useRowHeight(ref: RefObject<Element | null>, lines: number): RowHeights {
  const [height, setHeight] = useState<RowHeights>(() => read(null, lines));
  useLayoutEffect(() => {
    const update = () => {
      setHeight(read(ref.current, lines));
    };
    update();
    const observer = new MutationObserver(update);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-density'],
    });
    return () => {
      observer.disconnect();
    };
  }, [ref, lines]);
  return height;
}
