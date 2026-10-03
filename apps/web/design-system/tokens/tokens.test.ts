import { describe, expect, it } from 'vitest';

import { dark, light, SERIES, textPairs, type Palette } from './color';
import { AA_GRAPHIC, AA_TEXT, contrastRatio } from './contrast';
import { renderTokensCss } from './css';

const THEMES: [string, Palette][] = [
  ['dark', dark],
  ['light', light],
];

describe('contrastRatio', () => {
  it('matches the WCAG reference values', () => {
    expect(contrastRatio('#000000', '#ffffff')).toBeCloseTo(21, 5);
    expect(contrastRatio('#ffffff', '#ffffff')).toBeCloseTo(1, 5);
    expect(contrastRatio('#777777', '#ffffff')).toBeCloseTo(4.48, 2);
  });
});

describe.each(THEMES)('%s palette', (_name, palette) => {
  it('every text role passes AA (4.5:1) on the backgrounds it is used on', () => {
    const failures = textPairs(palette).flatMap(({ fgName, fg, bgs }) =>
      bgs
        .map((bg) => ({ bg, ratio: contrastRatio(fg, bg) }))
        .filter(({ ratio }) => ratio < AA_TEXT)
        .map(({ bg, ratio }) => `${fgName} ${fg} on ${bg}: ${ratio.toFixed(2)}`),
    );
    expect(failures).toEqual([]);
  });

  it('every series colour is a visible graphic (3:1) on bg and surface', () => {
    const failures = SERIES.flatMap((s) =>
      [palette.surface.bg, palette.surface.surface]
        .filter((bg) => contrastRatio(palette.series[s], bg) < AA_GRAPHIC)
        .map((bg) => `${s} on ${bg}`),
    );
    expect(failures).toEqual([]);
  });

  it('series colours are all different', () => {
    expect(new Set(Object.values(palette.series)).size).toBe(SERIES.length);
  });
});

describe('tokens.css', () => {
  it('is dark-first with light and system overrides', () => {
    const css = renderTokensCss();
    expect(css).toContain(`--color-bg: ${dark.surface.bg};`);
    expect(css).toContain(":root[data-theme='light']");
    expect(css).toContain('@media (prefers-color-scheme: light)');
    expect(css).toContain('@media (prefers-reduced-motion: reduce)');
  });
});
