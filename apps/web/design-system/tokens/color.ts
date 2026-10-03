/**
 * Colour tokens: FINAL (owner-approved mockups, 2026-10-03; ADR 0011). Dark-first, one accent.
 *
 * Every value here is a ROLE, never a raw step: components use `--color-<role>` only. Light and
 * dark are defined together with the same keys (a typed `Palette`), so a role cannot exist in
 * one theme and not the other. Contrast of every text role on bg / surface / row is listed on
 * the Storybook "Foundations/Tokens" page and checked by axe on every story in both themes.
 */

/** One status: a tinted background, its border and the foreground (text / icon) colour. */
export interface StatusColor {
  readonly bg: string;
  readonly border: string;
  readonly fg: string;
}

export const STATUSES = ['positive', 'warning', 'negative', 'neutral', 'info'] as const;
export type Status = (typeof STATUSES)[number];

/** Data-visualisation series, in fixed order (assign by entity, never cycle or re-rank). */
export const SERIES = ['s1', 's2', 's3', 's4', 's5', 's6'] as const;
export type Series = (typeof SERIES)[number];

export interface Palette {
  readonly surface: {
    /** The canvas behind everything. */
    readonly bg: string;
    /** Panels, the top bar, popovers. */
    readonly surface: string;
    /** Table row hover / zebra, inset wells. */
    readonly row: string;
    /** Panel and control borders. */
    readonly border: string;
    /** Dividers inside a panel (header rule, cell separators). */
    readonly borderSoft: string;
    /** Control outlines (inputs, segmented buttons, chips). */
    readonly control: string;
    /** Track of a bar / meter / slider. */
    readonly track: string;
    /** A heatmap cell with no data ("not collected"). */
    readonly empty: string;
  };
  readonly text: {
    readonly primary: string;
    /** Secondary text: inactive nav, legend values. */
    readonly secondary: string;
    /** Captions, column headers, units, metadata. */
    readonly muted: string;
  };
  readonly accent: {
    /** THE accent: links, primary button, focus ring, selected marks. */
    readonly accent: string;
    /** Text / icon on a solid accent fill. */
    readonly onAccent: string;
    /** Selected nav item, selected row, info background. */
    readonly soft: string;
    /** Text on `soft`; link hover. */
    readonly strong: string;
    /** Border of a selected / focused panel. */
    readonly border: string;
  };
  readonly status: Record<Status, StatusColor>;
  /** Price up / down: `standard` (green / red) and `cvd` (blue / orange, colour-blind safe). */
  readonly up: { readonly standard: string; readonly cvd: string };
  readonly down: { readonly standard: string; readonly cvd: string };
  readonly series: Record<Series, string>;
}

export const dark: Palette = {
  surface: {
    bg: '#0d0f12',
    surface: '#15181d',
    row: '#1b1f25',
    border: '#262a31',
    borderSoft: '#1f2329',
    control: '#333842',
    track: '#23272e',
    empty: '#1a1d22',
  },
  text: { primary: '#e8eaee', secondary: '#c3c7cf', muted: '#8b919c' },
  accent: {
    accent: '#4f7cff',
    // The Ideas / Main mockups put white on the accent (3.7:1, below AA); the Screener mockup's
    // dark-on-accent passes (5.2:1), so dark text on the accent is the token.
    onAccent: '#0d0f12',
    soft: '#1a2440',
    strong: '#a9bfff',
    border: '#2f4380',
  },
  status: {
    positive: { bg: '#0f2a24', border: '#1e5c4e', fg: '#5fd3b5' },
    warning: { bg: '#2e2312', border: '#6b4a17', fg: '#f0b55c' },
    negative: { bg: '#2f1517', border: '#6e2a2e', fg: '#f08a8a' },
    neutral: { bg: '#1b1f25', border: '#333842', fg: '#c3c7cf' },
    info: { bg: '#1a2440', border: '#2f4380', fg: '#a9bfff' },
  },
  up: { standard: '#5fd3b5', cvd: '#56b4e9' },
  down: { standard: '#f08a8a', cvd: '#e69f00' },
  series: {
    s1: '#4f7cff',
    s2: '#f0b55c',
    s3: '#5fd3b5',
    s4: '#a04ab3',
    s5: '#bcb2fd',
    s6: '#586e1c',
  },
};

export const light: Palette = {
  surface: {
    bg: '#f7f7f5',
    surface: '#ffffff',
    row: '#f1f1ee',
    border: '#e3e3df',
    borderSoft: '#ecece8',
    control: '#d4d4cf',
    track: '#f0f0ec',
    empty: '#f0f0ec',
  },
  text: { primary: '#16181d', secondary: '#3d424d', muted: '#5b606b' },
  accent: {
    accent: '#2446a8',
    onAccent: '#ffffff',
    soft: '#eef1fa',
    strong: '#16306f',
    border: '#b8c4ea',
  },
  status: {
    positive: { bg: '#eaf6f2', border: '#a9d6c9', fg: '#0b5d4f' },
    warning: { bg: '#fdf3e3', border: '#e6b26b', fg: '#8a4b00' },
    negative: { bg: '#fbecec', border: '#e5a3a3', fg: '#8f1d1d' },
    neutral: { bg: '#f1f1ee', border: '#d4d4cf', fg: '#3d424d' },
    info: { bg: '#eef1fa', border: '#b8c4ea', fg: '#16306f' },
  },
  up: { standard: '#0b5d4f', cvd: '#0b62a8' },
  down: { standard: '#8f1d1d', cvd: '#a14a00' },
  series: {
    s1: '#2446a8',
    s2: '#b45309',
    s3: '#0b5d4f',
    s4: '#540d2c',
    s5: '#8c5bd1',
    s6: '#4e986c',
  },
};

/** CSS variable name -> value for one palette (`--color-<name>`). */
export function colorRoles(palette: Palette, upDown: 'standard' | 'cvd'): [string, string][] {
  const { surface: s, text: t, accent: a } = palette;
  return [
    ['bg', s.bg],
    ['surface', s.surface],
    ['row', s.row],
    ['border', s.border],
    ['border-soft', s.borderSoft],
    ['control', s.control],
    ['track', s.track],
    ['empty', s.empty],
    ['text', t.primary],
    ['text-2', t.secondary],
    ['muted', t.muted],
    ['accent', a.accent],
    ['on-accent', a.onAccent],
    ['accent-soft', a.soft],
    ['accent-strong', a.strong],
    ['accent-border', a.border],
    ['focus-ring', a.accent],
    ...STATUSES.flatMap((name): [string, string][] => [
      [`${name}-bg`, palette.status[name].bg],
      [`${name}-border`, palette.status[name].border],
      [name, palette.status[name].fg],
    ]),
    ['up', palette.up[upDown]],
    ['down', palette.down[upDown]],
    ...SERIES.map((name): [string, string] => [name, palette.series[name]]),
  ];
}

/** Text colours and the backgrounds they must read on (AA 4.5:1), for the contrast check. */
export function textPairs(palette: Palette): { fg: string; fgName: string; bgs: string[] }[] {
  const backgrounds = [palette.surface.bg, palette.surface.surface, palette.surface.row];
  return [
    { fgName: 'text', fg: palette.text.primary, bgs: backgrounds },
    { fgName: 'text-2', fg: palette.text.secondary, bgs: backgrounds },
    { fgName: 'muted', fg: palette.text.muted, bgs: backgrounds },
    { fgName: 'accent', fg: palette.accent.accent, bgs: backgrounds.slice(0, 2) },
    { fgName: 'accent-strong', fg: palette.accent.strong, bgs: [palette.accent.soft] },
    { fgName: 'on-accent', fg: palette.accent.onAccent, bgs: [palette.accent.accent] },
    ...STATUSES.map((name) => ({
      fgName: name,
      fg: palette.status[name].fg,
      bgs: [...backgrounds, palette.status[name].bg],
    })),
    { fgName: 'up (standard)', fg: palette.up.standard, bgs: backgrounds },
    { fgName: 'down (standard)', fg: palette.down.standard, bgs: backgrounds },
    { fgName: 'up (cvd)', fg: palette.up.cvd, bgs: backgrounds },
    { fgName: 'down (cvd)', fg: palette.down.cvd, bgs: backgrounds },
  ];
}
