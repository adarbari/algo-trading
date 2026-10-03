/**
 * Colour tokens (DRAFT: pending owner approval of the mockups, ADR 0011).
 *
 * A neutral 12-step grey scale, ONE accent, semantic positive / negative / warning / info, and
 * up / down in two palettes: standard (green / red) and colour-blind safe (blue / orange,
 * Okabe-Ito). Light and dark are defined together; components use only the semantic roles
 * (`--color-bg-*`, `--color-fg-*`, `--color-border-*`, ...), never the raw steps.
 */

/** Twelve steps: 1-2 backgrounds, 3-5 interactive fills, 6-8 borders, 9-10 solids, 11-12 text. */
export type Scale = readonly [
  string,
  string,
  string,
  string,
  string,
  string,
  string,
  string,
  string,
  string,
  string,
  string,
];

export interface Palette {
  readonly gray: Scale;
  readonly accent: {
    readonly solid: string;
    readonly solidHover: string;
    readonly text: string;
    readonly subtle: string;
    readonly border: string;
    readonly onSolid: string;
  };
  readonly positive: string;
  readonly negative: string;
  readonly warning: string;
  readonly info: string;
  readonly up: { readonly standard: string; readonly cvd: string };
  readonly down: { readonly standard: string; readonly cvd: string };
}

export const light: Palette = {
  gray: [
    '#fcfcfc',
    '#f9f9f9',
    '#f0f0f0',
    '#e8e8e8',
    '#e0e0e0',
    '#d9d9d9',
    '#cecece',
    '#bbbbbb',
    '#8d8d8d',
    '#838383',
    '#646464',
    '#202020',
  ],
  accent: {
    solid: '#0d74ce',
    solidHover: '#0b68b9',
    text: '#0b68b9',
    subtle: '#e6f4fe',
    border: '#acd8fc',
    onSolid: '#ffffff',
  },
  positive: '#18794e',
  negative: '#ce2c31',
  warning: '#975a00',
  info: '#0b68b9',
  up: { standard: '#18794e', cvd: '#0d74ce' },
  down: { standard: '#ce2c31', cvd: '#bd4b00' },
};

export const dark: Palette = {
  gray: [
    '#111111',
    '#191919',
    '#222222',
    '#2a2a2a',
    '#313131',
    '#3a3a3a',
    '#484848',
    '#606060',
    '#6e6e6e',
    '#7b7b7b',
    '#b4b4b4',
    '#eeeeee',
  ],
  accent: {
    solid: '#0090ff',
    solidHover: '#3b9eff',
    text: '#70b8ff',
    subtle: '#0d2847',
    border: '#205d9e',
    onSolid: '#ffffff',
  },
  positive: '#3dd68c',
  negative: '#ff9592',
  warning: '#ffca16',
  info: '#70b8ff',
  up: { standard: '#3dd68c', cvd: '#70b8ff' },
  down: { standard: '#ff9592', cvd: '#ffa057' },
};

/** Semantic roles: name -> grey step (1-based) or a palette path. Components use only these. */
export const roles = {
  'bg-canvas': 'gray.1',
  'bg-surface': 'gray.2',
  'bg-subtle': 'gray.3',
  'bg-hover': 'gray.4',
  'bg-active': 'gray.5',
  'border-subtle': 'gray.6',
  'border-default': 'gray.7',
  'border-strong': 'gray.8',
  'fg-default': 'gray.12',
  'fg-muted': 'gray.11',
  'fg-disabled': 'gray.9',
  'accent-solid': 'accent.solid',
  'accent-solid-hover': 'accent.solidHover',
  'accent-text': 'accent.text',
  'accent-subtle': 'accent.subtle',
  'accent-border': 'accent.border',
  'on-accent': 'accent.onSolid',
  positive: 'positive',
  negative: 'negative',
  warning: 'warning',
  info: 'info',
  'focus-ring': 'accent.solid',
} as const;

export type ColorRole = keyof typeof roles;
