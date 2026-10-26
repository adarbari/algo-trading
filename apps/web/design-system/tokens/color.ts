/**
 * Colour tokens: "Evening Desk" (owner-approved 2026-10-25; ADR 0085, amending ADR 0011). One accent,
 * soft dark and a warm light. Lamp = `warning`, sea-glass = `positive` / `up`, loss = `negative` / `down`.
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
    /** The top bar. */
    readonly bar: string;
    /** Panels, popovers. */
    readonly surface: string;
    /** Raised: table row hover / zebra, inset wells. */
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
    bg: '#121722',
    bar: '#171e2c',
    surface: '#1a2131',
    row: '#202839',
    border: '#263048',
    borderSoft: '#1f2738',
    control: '#364260',
    track: '#232c41',
    empty: '#2c3650',
  },
  text: { primary: '#eef1f6', secondary: '#c4cbd9', muted: '#a3acc0' },
  accent: {
    accent: '#aebdff',
    onAccent: '#121722',
    soft: '#252f4f',
    strong: '#aebdff',
    border: '#3a4a80',
  },
  status: {
    positive: { bg: '#173a33', border: '#2a6153', fg: '#6fd3b8' },
    warning: { bg: '#3a2c14', border: '#7a5b24', fg: '#f5c26b' },
    negative: { bg: '#3b2220', border: '#7a403a', fg: '#f4a38f' },
    neutral: { bg: '#202839', border: '#364260', fg: '#c4cbd9' },
    info: { bg: '#252f4f', border: '#3a4a80', fg: '#aebdff' },
  },
  up: { standard: '#6fd3b8', cvd: '#56b4e9' },
  down: { standard: '#f4a38f', cvd: '#e69f00' },
  series: {
    s1: '#aebdff',
    s2: '#f5c26b',
    s3: '#6fd3b8',
    s4: '#c58bd9',
    s5: '#e8e8f0',
    s6: '#d6706a',
  },
};

export const light: Palette = {
  surface: {
    bg: '#f4f6fb',
    bar: '#ffffff',
    surface: '#ffffff',
    row: '#eef1f8',
    border: '#dee3ee',
    borderSoft: '#e8ecf4',
    control: '#c9d0e0',
    track: '#e6eaf3',
    empty: '#dce1ec',
  },
  text: { primary: '#1a2033', secondary: '#3f4860', muted: '#5d667d' },
  accent: {
    accent: '#3e55c9',
    onAccent: '#ffffff',
    soft: '#e6eafb',
    strong: '#3346b0',
    border: '#bcc6f0',
  },
  status: {
    positive: { bg: '#e2f5ef', border: '#a6d9cb', fg: '#137560' },
    warning: { bg: '#fff4de', border: '#ebc884', fg: '#8a5a00' },
    negative: { bg: '#fbeae6', border: '#e5afa3', fg: '#ad4631' },
    neutral: { bg: '#eef1f8', border: '#c9d0e0', fg: '#3f4860' },
    info: { bg: '#e6eafb', border: '#bcc6f0', fg: '#3346b0' },
  },
  up: { standard: '#137560', cvd: '#0b62a8' },
  down: { standard: '#ad4631', cvd: '#a14a00' },
  series: {
    s1: '#3e55c9',
    s2: '#b45309',
    s3: '#137560',
    s4: '#c0408c',
    s5: '#2e7fb8',
    s6: '#191f7c',
  },
};

/** CSS variable name -> value for one palette (`--color-<name>`). */
export function colorRoles(palette: Palette, upDown: 'standard' | 'cvd'): [string, string][] {
  const { surface: s, text: t, accent: a } = palette;
  return [
    ['bg', s.bg],
    ['bar', s.bar],
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
  const backgrounds = [
    palette.surface.bg,
    palette.surface.bar,
    palette.surface.surface,
    palette.surface.row,
  ];
  return [
    { fgName: 'text', fg: palette.text.primary, bgs: backgrounds },
    { fgName: 'text-2', fg: palette.text.secondary, bgs: backgrounds },
    { fgName: 'muted', fg: palette.text.muted, bgs: backgrounds },
    { fgName: 'accent', fg: palette.accent.accent, bgs: backgrounds.slice(0, 3) },
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
