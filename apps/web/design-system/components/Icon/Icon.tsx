/**
 * Icon: the design system's small stroke icon set (16 px grid, 1.5 px stroke, round caps), drawn
 * in `currentColor` so it takes the colour of the text around it. Decorative by default (hidden
 * from screen readers); give `label` when the icon alone carries meaning. No emoji, no icon
 * fonts. `spinner` with `spin` is the loading indicator.
 */
import type { ReactNode } from 'react';

import styles from './Icon.module.css';

const PATHS = {
  close: <path d="M4 4l8 8M12 4l-8 8" />,
  plus: <path d="M8 3v10M3 8h10" />,
  minus: <path d="M3 8h10" />,
  search: (
    <>
      <circle cx="7" cy="7" r="4.25" />
      <path d="M10.25 10.25L13.5 13.5" />
    </>
  ),
  'chevron-down': <path d="M4 6l4 4 4-4" />,
  'chevron-up': <path d="M4 10l4-4 4 4" />,
  'chevron-left': <path d="M10 4L6 8l4 4" />,
  'chevron-right': <path d="M6 4l4 4-4 4" />,
  check: <path d="M3.5 8.5l3 3 6-7" />,
  alert: (
    <>
      <path d="M8 2.5l6 10.5H2z" />
      <path d="M8 6.75v2.75M8 11.25v0.01" />
    </>
  ),
  info: (
    <>
      <circle cx="8" cy="8" r="6" />
      <path d="M8 7.5v3.75M8 5.01v-0.01" />
    </>
  ),
  external: <path d="M9.5 2.5h4v4M13.5 2.5L8 8M11.5 9.5v4h-9v-9h4" />,
  'drag-handle': (
    <path d="M6 4v0.01M10 4v0.01M6 8v0.01M10 8v0.01M6 12v0.01M10 12v0.01" data-dots="" />
  ),
  refresh: <path d="M13 8a5 5 0 1 1-1.46-3.54M13.5 2.5v3h-3" />,
  filter: <path d="M2.5 3.5h11L9.25 8.5v4l-2.5 1.25V8.5z" />,
  columns: (
    <>
      <rect x="2.5" y="3" width="11" height="10" rx="1" />
      <path d="M6.17 3v10M9.83 3v10" />
    </>
  ),
  book: (
    <>
      <path d="M2 3h3.5A2.5 2.5 0 0 1 8 5.5V13a1.75 1.75 0 0 0-1.75-1.75H2z" />
      <path d="M14 3h-3.5A2.5 2.5 0 0 0 8 5.5V13a1.75 1.75 0 0 1 1.75-1.75H14z" />
    </>
  ),
  'zoom-in': (
    <>
      <circle cx="7" cy="7" r="4.25" />
      <path d="M10.25 10.25L13.5 13.5M5.25 7h3.5M7 5.25v3.5" />
    </>
  ),
  'zoom-out': (
    <>
      <circle cx="7" cy="7" r="4.25" />
      <path d="M10.25 10.25L13.5 13.5M5.25 7h3.5" />
    </>
  ),
  fit: <path d="M2.5 6V2.5H6M10 2.5h3.5V6M13.5 10v3.5H10M6 13.5H2.5V10" />,
  spinner: (
    <>
      <circle cx="8" cy="8" r="5.5" data-track="" />
      <path d="M8 2.5a5.5 5.5 0 0 1 5.5 5.5" />
    </>
  ),
} as const satisfies Record<string, ReactNode>;

export type IconName = keyof typeof PATHS;

/** Every icon in the set, in catalogue order. */
export const ICON_NAMES = Object.keys(PATHS) as IconName[];

export type IconTone =
  'inherit' | 'muted' | 'secondary' | 'accent' | 'positive' | 'warning' | 'negative' | 'info';

export interface IconProps {
  /** Which icon: close, plus, minus, search, chevron-*, check, alert, info, external, drag-handle, refresh, filter, columns, book, zoom-in, zoom-out, fit, spinner. */
  name: IconName;
  /** sm 12, md 14 (default), lg 16 px. */
  size?: 'sm' | 'md' | 'lg';
  /** Colour role; `inherit` (default) follows the surrounding text. */
  tone?: IconTone;
  /** Accessible name when the icon alone carries meaning; omit for decorative icons. */
  label?: string;
  /** Rotate continuously (the `spinner` loading indicator); still under reduced motion. */
  spin?: boolean;
}

export function Icon({ name, size = 'md', tone = 'inherit', label, spin = false }: IconProps) {
  return (
    <svg
      className={styles.icon}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      data-size={size}
      data-tone={tone}
      data-spin={spin || undefined}
      data-icon={name}
      focusable="false"
      {...(label ? { role: 'img', 'aria-label': label } : { 'aria-hidden': true })}
    >
      {PATHS[name]}
    </svg>
  );
}
